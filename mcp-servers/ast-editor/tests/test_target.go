package main

import (
	"fmt"
	"strings"
)

type Cache struct {
	capacity int
	items    map[string]string
}

func NewCache(capacity int) *Cache {
	return &Cache{capacity: capacity, items: make(map[string]string)}
}

func (c *Cache) Get(key string) string {
	return c.items[key]
}

func (c *Cache) Set(key, value string) {
	c.items[key] = value
}
