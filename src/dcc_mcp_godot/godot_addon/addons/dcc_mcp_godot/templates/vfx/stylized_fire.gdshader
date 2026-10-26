shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never;

uniform sampler2D noise_texture : repeat_enable, filter_linear_mipmap;
uniform sampler2D detail_texture : repeat_enable, filter_linear_mipmap;
uniform sampler2D color_ramp : source_color, repeat_disable, filter_linear;
uniform float scroll_speed : hint_range(0.0, 4.0) = 0.65;
uniform vec2 noise_scale = vec2(3.0, 1.4);
uniform vec2 detail_scale = vec2(5.0, 2.0);
uniform float erosion : hint_range(0.0, 1.0) = 0.4;
uniform float edge_softness : hint_range(0.001, 0.5) = 0.08;
uniform float sway : hint_range(0.0, 1.0) = 0.18;
uniform float twist : hint_range(-4.0, 4.0) = 0.9;
uniform float emission_strength : hint_range(0.0, 8.0) = 1.6;
uniform float dissolve : hint_range(0.0, 1.0) = 0.0;

void vertex() {
	float height = clamp(1.0 - UV.y, 0.0, 1.0);
	float angle = twist * height + sin(TIME * 1.4) * height * 0.25;
	mat2 rotation = mat2(vec2(cos(angle), sin(angle)), vec2(-sin(angle), cos(angle)));
	VERTEX.xz = rotation * VERTEX.xz * (1.0 - 0.7 * pow(height, 1.2));
	VERTEX.x += sin(TIME * 2.1 + height * 5.0) * sway * height * height;
	VERTEX.z += cos(TIME * 1.7 + height * 4.0) * sway * height * height;
}

void fragment() {
	float height = clamp(1.0 - UV.y, 0.0, 1.0);
	vec2 flow = vec2(TIME * scroll_speed * 0.12, TIME * scroll_speed);
	vec2 swirl = vec2(height * twist * 0.12, 0.0);
	float body = texture(noise_texture, UV * noise_scale + flow + swirl).r;
	float detail = texture(detail_texture, UV * detail_scale + flow * vec2(-0.7, 1.35) - swirl).r;
	float density = body * 0.9 - detail * erosion - height * 0.65 + 0.2;
	float alpha = smoothstep(0.0, max(edge_softness, 0.001), density - dissolve * 1.2);
	alpha *= smoothstep(0.0, 0.04, height) * (1.0 - smoothstep(0.8, 1.0, height));
	vec3 fire_color = texture(color_ramp, vec2(clamp(height + detail * 0.12, 0.0, 1.0), 0.5)).rgb;
	// Compatibility ignores EMISSION on unshaded materials.
	ALBEDO = fire_color * emission_strength;
	ALPHA = alpha * (1.0 - clamp(dissolve, 0.0, 1.0));
}
