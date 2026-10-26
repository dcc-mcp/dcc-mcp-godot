# Texture sources for reusable VFX

[Simon Schreibt's Textures for VFX Database](https://simonschreibt.notion.site/Textures-for-VFX-Database-2c72eccccfa84a0eae927d778ad746cc)
is a source-discovery index for packs, brushes, generators, footage, and learning
material. Select the underlying source for the needed shape, then inspect its
own usage terms; the index does not grant one license to everything it links.

The default mesh fire uses `NoiseTexture2D` and a gradient; dynamic fire builds
its own fire and spark masks; circles, slashes, trails and impact breakup are
procedural shaders. None requires an image from the index or a tutorial. Keep
this default when a game has no cleared external texture source. The private
mage's generated PBR maps belong to the character asset's separate provenance;
they are not a license dependency of the procedural fallback or effect library.

For dynamic fire, choose a grayscale or alpha image with irregular lobes,
fine internal detail, and no hard rectangular boundary. For sparks and glows,
use compact soft masks. A texture that looks good alone may become solid white
when dozens of quads overlap: evaluate it in the final particle material.

The [dynamic fire tutorial](https://www.youtube.com/watch?v=Y1ZBzIiP-v4)
links an [author-provided Drive folder](https://drive.google.com/drive/folders/1dJf69ivpAyGwpRo9BjJOtGusFmhPEYMS)
containing `T_fire01.png` and `T_VFX_Glow_1.PNG`. These are useful references and
optional local inputs. No redistribution license was found in that folder at
inspection, so they are not bundled in this skill. The default effect creates
its own procedural textures and is usable without those files.

For each chosen external asset, retain the original name, source URL, hash,
license/permission evidence, and intended use next to the project's asset
manifest. Import the image into Godot and pass its `res://` path to
`create_dynamic_fire_vfx`. Confirm it loads as `Texture2D`, then tune the
particle opacity, scale, and erosion against the actual background and camera.
Keep grayscale data masks separate from color imagery when configuring color
space, compression, filtering, and mipmaps.
