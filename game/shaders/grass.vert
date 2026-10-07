#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform float elapsed;
uniform float shadowOn;
uniform float grassLod;
uniform struct p3d_LightSourceParameters {
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
} p3d_LightSource[1];
in vec4 p3d_Vertex;
in vec4 p3d_Color;
in vec3 p3d_MultiTexCoord0;   // raiz da lamina (mundo)
out vec3 color;
void main() {
    vec3 root = p3d_MultiTexCoord0;
    vec4 v = p3d_Vertex;
    // Alpha da cor = peso do vento (base 0, ponta 1). Coordenadas ja sao globais.
    float w = p3d_Color.a;
    float gust = sin(elapsed * 0.7 + v.x * 0.05 + v.y * 0.04);
    float wave = sin(elapsed * 2.1 + v.x * 0.35 + v.y * 0.27);
    float flutter = sin(elapsed * 5.3 + v.x * 1.7 + v.y * 1.3);
    v.x += (0.05 + 0.04 * gust) * (wave + 0.25 * flutter) * w;
    v.y += 0.02 * wave * w;
    v.z -= 0.012 * abs(wave) * w;

    vec4 viewRoot = p3d_ModelViewMatrix * vec4(root, 1.0);
    float fade = 1.0 - smoothstep(55.0, 90.0, length(viewRoot.xyz));
    // Cinco vertices por lamina; as tres extras somem antes da troca de LOD.
    if (grassLod < 0.5 && (gl_VertexID / 5) % 5 >= 2) {
        fade *= 1.0 - smoothstep(14.0, 24.0, length(viewRoot.xyz));
    }
    v.xyz = mix(vec3(root.xy, root.z - 0.15), v.xyz, fade);

    // A sombra na raiz evita cintilacao entre os vertices da mesma lamina.
    float lit = 1.0;
    if (shadowOn > 0.5) {
        vec4 sc = p3d_LightSource[0].shadowViewMatrix * viewRoot;
        lit = textureProj(p3d_LightSource[0].shadowMap, sc);
    }
    color = p3d_Color.rgb * mix(0.5, 1.0, lit);
    gl_Position = p3d_ModelViewProjectionMatrix * v;
}
