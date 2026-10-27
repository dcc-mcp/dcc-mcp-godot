shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, blend_add;

uniform int effect_kind = 2;
uniform int aura_layer = 0;
uniform vec4 tint : source_color = vec4(0.3, 0.8, 1.0, 1.0);
uniform float progress = 0.0;
uniform float elapsed = 0.0;
uniform float opacity = 0.0;
uniform float accent = 0.0;

float stroke(float distance, float width) {
	float aa = max(fwidth(distance), 0.0015);
	return 1.0 - smoothstep(width, width + aa, abs(distance));
}

float segment(vec2 p, vec2 a, vec2 b, float width) {
	vec2 span = b - a;
	float along = clamp(dot(p - a, span) / dot(span, span), 0.0, 1.0);
	return stroke(length(p - a - span * along), width);
}

float rune_band(float r, float angle) {
	float cell = floor(angle / TAU * 24.0);
	vec2 tile = vec2((fract(angle / TAU * 24.0) - 0.5) * 2.0, (r - 0.79) / 0.055);
	float seed = fract(sin(cell * 12.9898) * 43758.5453);
	float lines = segment(tile, vec2(-0.28, -0.65), vec2(-0.28, 0.65), 0.055);
	lines += segment(tile, vec2(-0.28, 0.55), vec2(0.35, 0.0), 0.055);
	lines += segment(tile, vec2(-0.28, -0.2), vec2(0.35, 0.35 - seed), 0.055);
	lines += segment(tile, vec2(0.35, -0.65), vec2(0.35, -0.05), 0.055) * step(0.48, seed);
	return min(lines, 1.0) * (1.0 - smoothstep(0.93, 1.0, abs(tile.y)));
}

float triangles(vec2 p) {
	float lines = segment(p, vec2(0.0, -0.39), vec2(0.338, 0.195), 0.006);
	lines += segment(p, vec2(0.338, 0.195), vec2(-0.338, 0.195), 0.006);
	lines += segment(p, vec2(-0.338, 0.195), vec2(0.0, -0.39), 0.006);
	lines += segment(p, vec2(0.0, 0.39), vec2(-0.338, -0.195), 0.006);
	lines += segment(p, vec2(-0.338, -0.195), vec2(0.338, -0.195), 0.006);
	lines += segment(p, vec2(0.338, -0.195), vec2(0.0, 0.39), 0.006);
	return lines;
}

void fragment() {
	vec2 p = UV * 2.0 - 1.0;
	float r = length(p);
	float angle = atan(p.y, p.x);
	float shape = 0.0;
	float glow = 0.0;
	float life = 1.0;
	if (effect_kind == 0) {
		// The swipe sweeps a forward-facing crescent; its trailing edge thins away.
		float head = mix(-2.8, -0.35, smoothstep(0.0, 0.65, progress));
		float behind = head - angle;
		float tail = (1.0 - smoothstep(0.0, 1.75, behind)) * step(0.0, behind);
		float radius = 0.70 + progress * 0.18;
		shape = stroke(r - radius, 0.012 + 0.065 * tail) * tail;
		shape += stroke(r - radius + 0.09, 0.008) * tail * 0.45;
		glow = exp(-abs(r - radius) * 24.0) * tail * 0.20;
		life = smoothstep(0.0, 0.08, progress) * (1.0 - smoothstep(0.60, 1.0, progress));
	} else if (effect_kind == 1) {
		float expansion = 1.0 - pow(1.0 - clamp(progress / 0.32, 0.0, 1.0), 3.0);
		float front = mix(0.05, 0.95, expansion);
		float strike = 1.0 - smoothstep(0.20, 0.68, progress);
		shape = stroke(r - front, mix(0.035, 0.009, expansion)) * strike;
		shape += stroke(r - front + 0.045, 0.008) * strike * 0.45;
		float return_phase = smoothstep(0.32, 1.0, progress);
		float returning = mix(0.94, 0.32, return_phase);
		shape += stroke(r - returning, 0.011) * smoothstep(0.24, 0.40, progress) * (1.0 - return_phase) * 0.65;
		float rays = pow(max(0.0, cos(angle * 12.0 + 0.3)), 18.0);
		shape += rays * smoothstep(front * 0.4, front * 0.6, r) * (1.0 - smoothstep(front * 0.80, front, r)) * strike * 0.55;
		glow = exp(-abs(r - front) * 30.0) * strike * 0.24 + exp(-r * 14.0) * (1.0 - smoothstep(0.0, 0.12, progress));
		life = 1.0 - smoothstep(0.78, 1.0, progress);
	} else {
		float a = angle + elapsed * 0.13;
		float b = angle - elapsed * 0.19;
		shape = stroke(r - 0.95, 0.006) + stroke(r - 0.91, 0.003);
		shape += stroke(r - 0.70, 0.006) + stroke(r - 0.67, 0.003);
		shape += stroke(r - 0.53, 0.025) * pow(max(0.0, cos(a * 16.0)), 26.0);
		float rotation = elapsed * 0.09;
		vec2 inner = mat2(vec2(cos(rotation), sin(rotation)), vec2(-sin(rotation), cos(rotation))) * p;
		if (aura_layer == 1) {
			shape = rune_band(r, a) + stroke(r - 0.86, 0.003) + stroke(r - 0.72, 0.003);
			shape += stroke(r - 0.88, 0.012) * smoothstep(0.22, 0.30, fract(b / TAU * 8.0));
		} else if (aura_layer == 2) {
			shape = triangles(inner) + stroke(r - 0.44, 0.005) + stroke(r - 0.18, 0.003);
			shape += stroke(r - 0.08, 0.008);
		}
		glow = exp(-abs(r - 0.8) * 30.0) * (0.025 + accent * 0.045);
		life = 0.9 + 0.1 * sin(elapsed * 2.0);
	}
	float edge = 1.0 - smoothstep(0.97, 1.0, r);
	float mask = clamp(shape + glow, 0.0, 1.0) * life * opacity * edge;
	float energy_flow = effect_kind == 2 ? 0.90 + 0.10 * sin(angle * 3.0 - elapsed * 2.0) : 1.0;
	ALBEDO = mix(tint.rgb, vec3(1.0), min(shape, 1.0) * 0.06) * (1.4 + accent * 0.55) * energy_flow;
	ALPHA = mask * tint.a;
}
