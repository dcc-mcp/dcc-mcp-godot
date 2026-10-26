shader_type spatial;

uniform bool enabled = false;
uniform int steps = 1;
uniform uint unsigned_value = 0u;
uniform bvec2 toggles = bvec2(false);
uniform float strength = 1.0;
uniform vec2 uv_scale = vec2(1.0);
uniform vec3 direction = vec3(0.0);
uniform vec4 weights = vec4(0.0);
uniform vec4 tint : source_color = vec4(1.0);
uniform sampler2D image;

void fragment() {
	ALBEDO = tint.rgb;
}
