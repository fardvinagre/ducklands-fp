#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform sampler2D waveField;
uniform float fieldSize;
in vec4 p3d_Vertex;
in vec4 p3d_Color;
out vec2 uv;
out vec3 worldPosition;
void main() {
    uv = p3d_Color.rg;
    vec4 vertex = p3d_Vertex;
    vertex.z += texture(waveField, (uv * (fieldSize - 1.0) + 0.5) / fieldSize).r;
    worldPosition = vertex.xyz;
    gl_Position = p3d_ModelViewProjectionMatrix * vertex;
}
