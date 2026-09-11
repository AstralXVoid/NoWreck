// Realistic module: a small LRU cache.
package cache

type Cache struct {
	capacity int
	store    map[string]*entry
	order    []string
}

type entry struct {
	key   string
	value string
	tags  []string
}

func New(capacity int) *Cache {
	return &Cache{
		capacity: capacity,
		store:    make(map[string]*entry),
		order:    make([]string, 0, capacity),
	}
}

func (c *Cache) Get(key string) (string, bool) {
	e, ok := c.store[key]
	if !ok {
		return "", false
	}
	c.touch(key)
	return e.value, true
}

func (c *Cache) Set(key, value string, tags []string) {
	if len(c.store) >= c.capacity {
		if _, ok := c.store[key]; !ok {
			c.evict()
		}
	}
	c.store[key] = &entry{key: key, value: value, tags: tags}
	c.order = append(c.order, key)
}

func (c *Cache) Len() int {
	return len(c.store)
}

func (c *Cache) touch(key string) {
	kept := c.order[:0]
	for _, k := range c.order {
		if k != key {
			kept = append(kept, k)
		}
	}
	c.order = append(kept, key)
}

func (c *Cache) evict() {
	if len(c.order) == 0 {
		return
	}
	oldest := c.order[0]
	c.order = c.order[1:]
	delete(c.store, oldest)
}

func Slugify(text string) string {
	var out strings.Builder
	for _, r := range strings.ToLower(text) {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			out.WriteRune(r)
		} else {
			out.WriteByte('-')
		}
	}
	return strings.Trim(out.String(), "-")
}

func Process(records [][2]string, c *Cache) []string {
	var out []string
	for _, record := range records {
		key := Slugify(record[0])
		if value, ok := c.Get(key); ok {
			out = append(out, "cached:"+value)
		} else {
			c.Set(key, record[1], nil)
			out = append(out, "fresh:"+key)
		}
	}
	return out
}
