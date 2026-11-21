using System;
using System.Collections.Generic;

namespace CubeCoachGame
{
    [Serializable]
    public class Point
    {
        public float x, y;

        public Point(float x, float y)
        {
            this.x = x;
            this.y = y;
        }
    }

    [Serializable]
    public class Level
    {
        public string title, description;
        public float seconds = 40;
        public Point[] goals, obstacles;
    }

    [Serializable]
    public class InputEvent
    {
        public float time;
        public int mask;
        public Point position;
    }

    [Serializable]
    public class Hit
    {
        public float time;
        public int goal;
    }

    [Serializable]
    public class Run
    {
        public string id;
        public Level level;
        public List<InputEvent> inputs = new();
        public List<Hit> hits = new();
        public float duration, distance;
        public string endReason;
        public bool completed;
        public Point finalPosition;
    }

    [Serializable]
    public class Review
    {
        public int rating;
        public string feedback, source;
        public Level nextLevel;
    }
}
