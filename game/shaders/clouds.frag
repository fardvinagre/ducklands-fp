#version 130
uniform sampler2D clouds;
uniform vec3 camPos;
uniform vec3 sunDir;
uniform vec3 haze;
uniform vec3 layer0;     // altitude, 1/tile
uniform vec3 layer1;
uniform vec2 wind0;
uniform vec2 wind1;
uniform float cloudTime;
uniform float coverage;
in vec3 dir;
out vec4 fragColor;

float density(vec2 uv, vec4 shapeMask, vec4 detailMask) {
    vec4 s = texture(clouds, uv);
    float shape = dot(s, shapeMask);
    float detail = dot(s, detailMask);
    return smoothstep(coverage, coverage + 0.18, shape + (detail - 0.5) * 0.28);
}

vec4 cloudLayer(vec3 d, vec3 layer, vec2 wind, vec4 shapeMask, vec4 detailMask) {
    float t = (layer.x - camPos.z) / d.z;
    vec2 uv = (camPos.xy + d.xy * t) * layer.y + wind * cloudTime;
    float dens = density(uv, shapeMask, detailMask);
    // A amostra na direcao do sol estima a sombra da propria nuvem.
    float toSun = density(uv + sunDir.xy * 0.012, shapeMask, detailMask);
    float lit = clamp(0.62 + (dens - toSun) * -0.9 + (1.0 - dens) * 0.35, 0.0, 1.0);
    vec3 shadow = vec3(0.70, 0.74, 0.82);
    vec3 sun = vec3(1.0, 0.98, 0.93);
    vec3 col = mix(shadow, sun, lit);
    float distanceFade = 1.0 - smoothstep(1800.0, 5200.0, t);
    col = mix(haze, col, distanceFade * 0.85 + 0.15);
    return vec4(col, dens * distanceFade * 0.92);
}

void main() {
    vec3 d = normalize(dir);
    if (d.z < 0.03) discard;
    float horizon = smoothstep(0.03, 0.22, d.z);
    vec4 far = cloudLayer(d, layer1, wind1, vec4(0, 1, 0, 0), vec4(0, 0, 0, 1));
    vec4 near = cloudLayer(d, layer0, wind0, vec4(1, 0, 0, 0), vec4(0, 0, 1, 0));
    // Camada proxima por cima da distante (alpha "over").
    float a = near.a + far.a * (1.0 - near.a);
    vec3 c = a > 0.001 ? (near.rgb * near.a + far.rgb * far.a * (1.0 - near.a)) / a : near.rgb;
    fragColor = vec4(c, a * horizon);
}
