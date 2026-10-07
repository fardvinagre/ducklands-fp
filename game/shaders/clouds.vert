#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
out vec3 dir;
void main() {
    // A cupula acompanha a camera sem rotacao: posicao local = direcao no mundo.
    dir = p3d_Vertex.xyz;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
