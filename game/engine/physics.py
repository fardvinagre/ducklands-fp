import math


def resolve_horizontal(x,y,obstacles,radius=.35):
    """Resolve circulos no plano XY, usado pelo controlador cinemático."""
    for ox,oy,other_radius in obstacles:
        dx,dy = x-ox,y-oy
        distance = math.hypot(dx,dy)
        minimum = radius+other_radius
        if distance < minimum:
            if distance < 1e-8:
                x = ox+minimum
            else:
                x,y = ox+dx/distance*minimum,oy+dy/distance*minimum
    return x,y
