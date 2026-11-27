shader_type canvas_item;

// Round DMD dots for the game's 128x32 picture on the large LCD (game/pup/pup_player.gd).
uniform vec2 dmd_size = vec2(128.0, 32.0);
uniform float dot_radius = 0.44;
uniform vec3 unlit = vec3(0.05, 0.02, 0.01);

void fragment() {
	vec4 c = texture(TEXTURE, UV);
	vec2 cell = fract(UV * dmd_size) - 0.5;
	float mask = 1.0 - smoothstep(dot_radius - 0.1, dot_radius, length(cell));
	COLOR = vec4(max(c.rgb, unlit) * mask, 1.0);
}
