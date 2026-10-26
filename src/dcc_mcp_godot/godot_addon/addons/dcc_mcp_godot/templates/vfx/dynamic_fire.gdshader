shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, blend_mix;

uniform sampler2D fire_texture : repeat_enable, filter_linear;
uniform sampler2D heat_ramp : source_color, repeat_disable, filter_linear;
uniform vec4 tint : source_color = vec4(1.0, 0.25, 0.035, 1.0);
uniform float intensity = 2.8;
uniform float texture_scale = 1.65;
uniform float scroll_speed = 0.22;
uniform float edge_softness = 0.13;
uniform float density = 0.62;
uniform float dissolve = 0.0;

varying float particle_age;
varying vec2 noise_offset;

void vertex() {
	// Preserve each particle's size while facing its quad towards the camera.
	mat4 facing = mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	facing[0].xyz *= length(MODEL_MATRIX[0].xyz);
	facing[1].xyz *= length(MODEL_MATRIX[1].xyz);
	facing[2].xyz *= length(MODEL_MATRIX[2].xyz);
	MODELVIEW_MATRIX = VIEW_MATRIX * facing;
	float angle = INSTANCE_CUSTOM.x;
	VERTEX.xy = mat2(vec2(cos(angle), sin(angle)), vec2(-sin(angle), cos(angle))) * VERTEX.xy;
	particle_age = INSTANCE_CUSTOM.y;
	float seed = float(INSTANCE_ID) * 0.6180339887;
	noise_offset = vec2(fract(seed), fract(seed * 1.713));
}

void fragment() {
	vec2 p = UV * 2.0 - 1.0;
	vec2 flow_uv = UV * texture_scale + noise_offset - vec2(0.0, TIME * scroll_speed);
	float broad = texture(fire_texture, flow_uv).r;
	float detail = texture(fire_texture, flow_uv * 2.17 + vec2(0.31, TIME * 0.08)).r;
	// Several overlapping, round particles form billowing volume instead of a cone.
	float field = density + broad * 0.50 + detail * 0.10 - dot(p, p) * 0.72;
	float erosion = smoothstep(0.30, 1.0, particle_age) * 0.54 + dissolve;
	float mask = smoothstep(erosion, erosion + edge_softness, field - 0.31);
	float rim = 1.0 - smoothstep(0.55, 1.0, length(p));
	float fade = smoothstep(0.0, 0.12, particle_age) * (1.0 - smoothstep(0.60, 1.0, particle_age));
	float heat = clamp((field - erosion - 0.30) * 1.30, 0.0, 1.0);
	vec3 palette = texture(heat_ramp, vec2(heat, 0.5)).rgb;
	vec3 outer = tint.rgb * palette.r;
	vec3 hot = mix(tint.rgb, vec3(1.0, 0.93, 0.72), 0.84) * palette;
	// Unshaded materials use ALBEDO, including HDR values, on all renderers.
	ALBEDO = mix(outer, hot, smoothstep(0.35, 0.95, heat)) * intensity;
	ALPHA = clamp(mask * rim * fade * tint.a, 0.0, 0.93);
}
