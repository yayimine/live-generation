using System;
using System.Collections.Generic;
using UnityEngine;
using Object = UnityEngine.Object;

namespace CubeCoachGame
{
    internal sealed class ArenaView : IDisposable
    {
        private static readonly Color Cyan = new(0.25f, 0.9f, 0.85f);
        private static readonly Color Gold = new(1f, 0.79f, 0.23f);
        private static readonly Color Grid = new(0.10f, 0.15f, 0.20f);

        private readonly Transform root;
        private readonly Texture2D texture;
        private readonly Sprite square;
        private readonly Transform player;
        private readonly List<GameObject> goals = new();
        private int shownHits;

        internal ArenaView(Transform parent)
        {
            root = new GameObject("Arena").transform;
            root.SetParent(parent, false);

            var camera = Camera.main;
            if (camera == null)
            {
                camera = new GameObject("Camera").AddComponent<Camera>();
                camera.transform.SetParent(root, false);
            }
            camera.orthographic = true;
            camera.orthographicSize = 7.6f;
            camera.transform.position = new Vector3(0, 0, -10);
            camera.backgroundColor = new Color(0.035f, 0.055f, 0.09f);

            texture = new Texture2D(1, 1);
            texture.SetPixel(0, 0, Color.white);
            texture.Apply();
            square = Sprite.Create(texture, new Rect(0, 0, 1, 1), new Vector2(0.5f, 0.5f), 1);

            const int width = ArenaRules.HalfWidth;
            const int height = ArenaRules.HalfHeight;
            for (int x = -width; x <= width; x++)
                Box("Grid", new Vector2(x, 0), new Vector2(0.015f, height * 2), Grid);
            for (int y = -height; y <= height; y++)
                Box("Grid", new Vector2(0, y), new Vector2(width * 2, 0.015f), Grid);
            foreach (int side in new[] { -1, 1 })
            {
                Box("Border", new Vector2(0, side * (height + 0.12f)),
                    new Vector2(width * 2 + 0.2f, 0.04f), Cyan);
                Box("Border", new Vector2(side * (width + 0.12f), 0),
                    new Vector2(0.04f, height * 2 + 0.2f), Cyan);
            }

            player = Box("Player", Vector2.zero, Vector2.one * ArenaRules.PlayerSize, Cyan, 3).transform;
        }

        internal void ShowLevel(Level level)
        {
            foreach (var goal in goals)
            {
                goal.SetActive(false);
                Object.Destroy(goal);
            }
            goals.Clear();

            foreach (var point in level.goals)
            {
                goals.Add(Box("Yellow goal", new Vector2(point.x, point.y),
                    Vector2.one * ArenaRules.GoalSize, Gold, 2));
            }

            player.position = Vector3.zero;
            shownHits = 0;
        }

        internal void Draw(RunSession session)
        {
            player.position = session.Position;
            var hits = session.Replay.hits;
            while (shownHits < hits.Count)
                goals[hits[shownHits++].goal].SetActive(false);
        }

        private GameObject Box(string name, Vector2 position, Vector2 size, Color color, int order = 0)
        {
            var box = new GameObject(name);
            box.transform.SetParent(root, false);
            box.transform.position = position;
            box.transform.localScale = size;
            var renderer = box.AddComponent<SpriteRenderer>();
            renderer.sprite = square;
            renderer.color = color;
            renderer.sortingOrder = order;
            return box;
        }

        public void Dispose()
        {
            Object.Destroy(root.gameObject);
            Object.Destroy(square);
            Object.Destroy(texture);
        }
    }
}
