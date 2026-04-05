package com.example;

import java.util.HashMap;
import java.util.Map;

public class LRUCache {
    private int capacity;
    private Map<String, String> items;

    public LRUCache(int capacity) {
        this.capacity = capacity;
        this.items = new HashMap<>();
    }

    @Override
    public String toString() {
        return "LRUCache";
    }

    public String get(String key) {
        return items.get(key);
    }
}
