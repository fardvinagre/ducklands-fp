import math
from collections import defaultdict


class SpatialGrid:
    def __init__(self, cell_size=8):
        self.cell_size = cell_size
        self.cells = defaultdict(list)

    def rebuild(self, objects):
        self.cells.clear()
        for obj in objects:
            self.cells[self.key(obj.x,obj.y)].append(obj)

    def key(self,x,y):
        return math.floor(x/self.cell_size),math.floor(y/self.cell_size)

    def nearby(self,x,y,radius):
        lo, hi = self.key(x-radius,y-radius),self.key(x+radius,y+radius)
        for cx in range(lo[0],hi[0]+1):
            for cy in range(lo[1],hi[1]+1):
                yield from self.cells.get((cx,cy),())
