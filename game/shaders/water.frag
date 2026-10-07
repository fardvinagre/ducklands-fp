#version 130
uniform sampler2D waveField;
uniform float fieldSize;
uniform float waterTime;
uniform vec3 waterEye;
in vec2 uv;
in vec3 worldPosition;
out vec4 fragColor;
void main() {
    vec4 field = texture(waveField, (uv * (fieldSize - 1.0) + 0.5) / fieldSize);
    float depth = max(0.0, field.a + field.r);
    if (depth < 0.015) discard;
    float shore = smoothstep(0.02, 0.35, depth);
    vec2 p = worldPosition.xy;
    float a = dot(p,vec2(1.5,0.9)) + waterTime*1.3 + 0.45*sin(p.y*0.37);
    float b = dot(p,vec2(-0.8,2.1)) - waterTime*1.6 + 0.4*sin(p.x*0.31);
    float c = dot(p,vec2(3.7,-2.5)) + waterTime*2.2;
    float modulation = 0.7 + 0.3*sin(dot(p,vec2(0.25,0.19))-waterTime*0.4);
    vec2 wind = (vec2(1.5,0.9)*cos(a)*0.010 + vec2(-0.8,2.1)*cos(b)*0.008
                + vec2(3.7,-2.5)*cos(c)*0.002) * shore * modulation;
    vec3 normal = normalize(vec3(-field.g * 4.0 - wind.x, -field.b * 4.0 - wind.y, 1.0));
    vec3 view = normalize(waterEye - worldPosition);
    if (view.z < 0.0) normal = -normal;
    float fresnel = 0.02 + 0.98 * pow(1.0 - max(dot(normal,view),0.0), 5.0);
    vec3 reflected = reflect(-view, normal);
    // Reflexo analitico do ceu, sem uma segunda renderizacao da cena.
    vec3 sky = mix(vec3(0.72,0.81,0.84),vec3(0.34,0.58,0.77),clamp(reflected.z,0.0,1.0));
    vec3 sun = normalize(vec3(-0.45,-0.55,1.0));
    float glint = pow(max(dot(reflected,sun),0.0),180.0);
    vec3 transmission = mix(vec3(0.20,0.48,0.39),vec3(0.035,0.22,0.25),1.0-exp(-depth*1.6));
    vec3 color = mix(transmission,sky,fresnel) + vec3(1.0,0.88,0.65)*glint*0.7;
    float waveLight = clamp(dot(field.gb,vec2(-0.45,-0.55))*3.0 + field.r*0.9,-0.15,0.15);
    color += vec3(0.20,0.30,0.28)*waveLight*shore;
    float shoreline = (1.0-smoothstep(0.04,0.24,depth)) * shore;
    float crest = smoothstep(0.045,0.10,length(field.gb)) * 0.25;
    float pattern = 0.55 + 0.45*sin(p.x*9.0 + sin(p.y*7.0) + waterTime*1.8);
    color = mix(color,vec3(0.80,0.89,0.86),clamp(shoreline*pattern + crest,0.0,0.55));
    float alpha = mix(0.35,0.94,1.0-exp(-depth*2.2));
    alpha = mix(alpha,0.98,fresnel) * smoothstep(0.015,0.08,depth);
    float fog = clamp((length(waterEye-worldPosition)-90.0)/100.0,0.0,1.0);
    fragColor = vec4(mix(color,vec3(0.57,0.74,0.82),fog),alpha);
}
