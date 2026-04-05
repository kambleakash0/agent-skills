require 'json'

class LRUCache
  def initialize(capacity)
    @capacity = capacity
    @items = {}
  end

  def get(key)
    @items[key]
  end
end

def helper(x)
  x * 2
end
