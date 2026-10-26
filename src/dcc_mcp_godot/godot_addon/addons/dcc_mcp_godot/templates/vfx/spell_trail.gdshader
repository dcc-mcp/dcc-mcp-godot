shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never;

uniform vec4 tint : source_color = vec4(1.0, 0.24, 0.035, 1.0);
uniform int mode = 0;
uniform float intensity = 1.8;
uniform float opacity = 1.0;

varying vec3 volume_point;

void vertex() {
	if (mode == 2) {
		vec3 direction = normalize(VERTEX);
		float lobes = 0.82 + 0.05 * sin(direction.x * 4.0 + direction.y * 3.0) * sin(direction.z * 4.0 - direction.y * 2.0);
		lobes += 0.03 * sin(direction.y * 5.0 + direction.x * 3.0);
		VERTEX *= lobes * vec3(1.0, 0.88, 1.0);
	}
	volume_point = VERTEX;
}

void fragment() {
	float coverage;
	float heat;
	if (mode == 0) {
		float side = abs(UV.y * 2.0 - 1.0);
		float flow = 0.84 + 0.16 * sin(UV.x * 37.0 - TIME * 23.0 + sin(UV.x * 19.0 + TIME * 7.0));
		coverage = (1.0 - smoothstep(0.15, 1.0, side)) * smoothstep(0.0, 0.2, UV.x) * flow;
		heat = exp(-side * side * 30.0) * smoothstep(0.35, 1.0, UV.x) * 0.72;
	} else if (mode == 3) {
		vec2 p = UV * 2.0 - 1.0;
		float radius = length(p);
		float angle = atan(p.y, p.x);
		float spokes = pow(max(0.0, cos(angle * 9.0 + sin(angle * 3.0) * 0.7)), 22.0);
		coverage = spokes * smoothstep(0.14, 0.32, radius) * (1.0 - smoothstep(0.65, 1.0, radius));
		heat = 0.65;
	} else {
		float facing = clamp(dot(normalize(NORMAL), normalize(VIEW)), 0.0, 1.0);
		coverage = smoothstep(0.0, 0.6, facing);
		heat = pow(facing, 4.0);
		if (mode == 2) {
			float breakup = sin(volume_point.x * 11.0 + volume_point.y * 7.0) * sin(volume_point.y * 9.0 - volume_point.z * 6.0);
			breakup += 0.55 * sin(volume_point.z * 13.0 + volume_point.x * 5.0);
			coverage = smoothstep(0.04, 0.35, facing) * smoothstep(-0.2, 1.2, breakup) * (0.25 + 0.45 * (1.0 - facing));
			heat = 0.0;
		}
	}
	ALBEDO = mix(tint.rgb, vec3(1.0, 0.87, 0.57), heat) * intensity;
	ALPHA = coverage * opacity * tint.a;
}
