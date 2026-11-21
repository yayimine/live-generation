"""Stage a relocatable coach runtime for Apple Silicon Unity builds."""
import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--adapter', required=True, type=Path)
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        parser.error('Run this on Apple Silicon macOS using native arm64 Python.')
    if not shutil.which('uv'):
        parser.error('Install uv on the build machine first: https://docs.astral.sh/uv/')
    if not (args.model / 'config.json').is_file() or not any(args.model.glob('*.safetensors')):
        parser.error('--model must point to local Transformers weights with config.json and safetensors.')
    if not (args.adapter / 'adapter_config.json').is_file() or not (args.adapter / 'adapter_model.safetensors').is_file():
        parser.error('--adapter must point to a trained PEFT adapter with safetensors weights.')

    root = Path(__file__).resolve().parent
    destination = root / 'macos-runtime'
    if destination.exists():
        parser.error(f'Move the existing {destination} aside before preparing a replacement.')
    for source in (args.model.resolve(), args.adapter.resolve()):
        if source == root or source in root.parents:
            parser.error('Supply dedicated model and adapter directories outside the staging root.')

    with tempfile.TemporaryDirectory(prefix='.macos-prepare-', dir=root) as temp:
        temp = Path(temp)
        env = dict(os.environ, UV_PYTHON_INSTALL_DIR=str(temp / 'interpreters'),
                   UV_PYTHON_INSTALL_BIN='false')
        subprocess.run(['uv', '--no-cache', 'python', 'install', '3.12', '--no-bin'],
                       env=env, check=True)
        runtime = temp / 'runtime'
        runtime.mkdir()
        interpreter, = (temp / 'interpreters').glob('cpython-3.12*-macos-aarch64-*')
        interpreter.rename(runtime / 'python')
        python = runtime / 'python/bin/python3.12'
        subprocess.run(['uv', '--no-cache', 'pip', 'install', '--python', str(python),
                        '--target', str(runtime / 'packages'), '--only-binary', ':all:',
                        '-r', str(root / 'requirements.txt')], check=True)
        # Console scripts installed by uv can contain absolute shebangs. The game only imports packages.
        shutil.rmtree(runtime / 'packages/bin', ignore_errors=True)
        for filename in ('server.py', 'protocol.py'):
            shutil.copy2(root / filename, runtime)
        for name, source in (('model', args.model), ('adapter', args.adapter)):
            shutil.copytree(source, runtime / name,
                            ignore=shutil.ignore_patterns('.git', '.cache', 'checkpoint-*'))

        relocated = temp / 'relocated runtime'
        runtime.rename(relocated)
        env = dict(os.environ, PYTHONPATH=str(relocated / 'packages'), HF_HUB_OFFLINE='1')
        env.pop('PYTHONHOME', None)
        subprocess.run([str(relocated / 'python/bin/python3.12'), '-sB', 'server.py',
                        '--model', 'model', '--adapter', 'adapter', '--check-model'],
                       cwd=relocated, env=env, check=True)
        relocated.rename(destination)
    print(f'Coach staged at {destination}. Build macOS in Unity to include it.')


if __name__ == '__main__':
    main()
