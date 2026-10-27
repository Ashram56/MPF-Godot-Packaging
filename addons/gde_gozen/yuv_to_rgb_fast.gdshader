shader_type canvas_item;
render_mode unshaded;

// The common case of yuv_to_rgb_compatibility.gdshader (no rotation, no interlacing, no alpha plane), about 3x
// cheaper on the Raspberry Pi 4's GPU: unshaded (Godot's canvas lighting code left out) and no branches, the
// colour profile and range folded into k_y/k_u/k_v and offset by video_playback.gd. 1080p layer: ~6 ms instead of ~18.
uniform sampler2D y_data;
uniform sampler2D u_data;
uniform sampler2D v_data;
uniform vec3 k_y = vec3(1.0);
uniform vec3 k_u = vec3(0.0, -0.1873, 1.8556);
uniform vec3 k_v = vec3(1.5748, -0.4681, 0.0);
uniform vec3 offset = vec3(0.0, 0.5, 0.5);

varying vec4 modulate;

void vertex() {
	modulate = COLOR;
}

void fragment() {
	vec3 yuv = vec3(texture(y_data, UV).r, texture(u_data, UV).r, texture(v_data, UV).r) - offset;
	COLOR = vec4(k_y * yuv.x + k_u * yuv.y + k_v * yuv.z, 1.0) * modulate;
}
