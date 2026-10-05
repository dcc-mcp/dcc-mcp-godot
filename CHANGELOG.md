# Changelog

## [0.9.4](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.9.3...v0.9.4) (2026-10-05)


### Bug Fixes

* **godot:** reject whitespace-only source in validate_script ([8dc0188](https://github.com/dcc-mcp/dcc-mcp-godot/commit/8dc0188babecc67882200229bd45068c619af74a))
* **godot:** reject whitespace-only source in validate_script ([3ccf663](https://github.com/dcc-mcp/dcc-mcp-godot/commit/3ccf663123a0063b3c6b2c1d66fafc8c5f4592cd))
* **godot:** resolve validate_script script_path alias and reject empty paths ([b2fc12c](https://github.com/dcc-mcp/dcc-mcp-godot/commit/b2fc12cd5c1e831af6b1f7bdcacc8c56e83c5cdf))
* **godot:** resolve validate_script script_path alias and reject empty paths ([796e607](https://github.com/dcc-mcp/dcc-mcp-godot/commit/796e607583691b1a46b6473d6d5d9d9883ce2bbe)), closes [#37](https://github.com/dcc-mcp/dcc-mcp-godot/issues/37)
* **scene-preview:** correct preview contract wording and serialize tool descriptions ([909fa5e](https://github.com/dcc-mcp/dcc-mcp-godot/commit/909fa5e4278f18900b3b9f9e54d7e56679bf7ad7))
* **scene-preview:** correct render_scene_preview contract wording and serialize tool descriptions ([f2ebb79](https://github.com/dcc-mcp/dcc-mcp-godot/commit/f2ebb79fe6dff7c6703d110b48d77f60ccca78ff))


### Documentation

* **scene-preview:** publish the render_scene_preview contract and platform matrix ([#60](https://github.com/dcc-mcp/dcc-mcp-godot/issues/60)) ([cf8c0ae](https://github.com/dcc-mcp/dcc-mcp-godot/commit/cf8c0aeb962a493ffdb7719424f4ec3da7e33b0b))

## [0.9.3](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.9.2...v0.9.3) (2026-10-04)


### Documentation

* correct the typed action result envelope note and harden the smoke verify ([#56](https://github.com/dcc-mcp/dcc-mcp-godot/issues/56)) ([ccd7dcf](https://github.com/dcc-mcp/dcc-mcp-godot/commit/ccd7dcf4b97a48364c8e4a374679fa34ebdddec0))

## [0.9.2](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.9.1...v0.9.2) (2026-10-04)


### Bug Fixes

* read the report schema version through Core's own API ([#51](https://github.com/dcc-mcp/dcc-mcp-godot/issues/51)) ([1d628b5](https://github.com/dcc-mcp/dcc-mcp-godot/commit/1d628b5cb526c66e10bd48434c587138900ff6ed))

## [0.9.1](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.9.0...v0.9.1) (2026-10-02)


### Bug Fixes

* **scene-tree:** honour scene_path in get_scene_tree instead of silently returning the edited scene ([#49](https://github.com/dcc-mcp/dcc-mcp-godot/issues/49)) ([cf5f0b6](https://github.com/dcc-mcp/dcc-mcp-godot/commit/cf5f0b64b7b80f0cc2d8463be8d043abe7031eb6))
* **screenshot:** read the staged preview pixels once ([#47](https://github.com/dcc-mcp/dcc-mcp-godot/issues/47)) ([787780d](https://github.com/dcc-mcp/dcc-mcp-godot/commit/787780daa67df446dbc972290878094d2dec7846))

## [0.9.0](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.8.1...v0.9.0) (2026-09-29)


### Features

* render scene previews from an unattended windowed host ([e49154b](https://github.com/dcc-mcp/dcc-mcp-godot/commit/e49154b7fd9c26fbbe0a97f41f6568d29f14c944))


### Bug Fixes

* **install:** emit the Install SOP document schema version, not the artifact revision ([2aa6112](https://github.com/dcc-mcp/dcc-mcp-godot/commit/2aa61127a776d908b151d50ad98822b8b5757285))

## [0.8.1](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.8.0...v0.8.1) (2026-09-22)


### Bug Fixes

* **bridge:** deterministic guarded-commit cleanup on terminal timeout ([46155f0](https://github.com/dcc-mcp/dcc-mcp-godot/commit/46155f074b5216142388cf67d82e7ab5cfa091ba))
* **ci:** wait on gameplay liveness for the runtime peer ([#40](https://github.com/dcc-mcp/dcc-mcp-godot/issues/40)) ([d57eff7](https://github.com/dcc-mcp/dcc-mcp-godot/commit/d57eff7602fc4db56c399a95384c6422b569d86f))


### Documentation

* add canonical agent quickstart ([#35](https://github.com/dcc-mcp/dcc-mcp-godot/issues/35)) ([f010245](https://github.com/dcc-mcp/dcc-mcp-godot/commit/f0102453b23333d687b37b21cc3b614ff941407e))

## [0.8.0](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.7.1...v0.8.0) (2026-09-08)


### Features

* add Godot build size optimization skill ([cac09a1](https://github.com/dcc-mcp/dcc-mcp-godot/commit/cac09a1db307ef9867fbb3625ca35d7d4ec4c508))


### Bug Fixes

* fence typed action host commits ([65d7447](https://github.com/dcc-mcp/dcc-mcp-godot/commit/65d74473ab0ec7182502b0779bade285506c7559))
* support profile generation on Python 3.9 ([1006e36](https://github.com/dcc-mcp/dcc-mcp-godot/commit/1006e362651001351dee50554347a274e9b08dc9))

## [0.7.1](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.7.0...v0.7.1) (2026-08-29)


### Performance Improvements

* enforce budgets for Godot built-in captures and reads ([#30](https://github.com/dcc-mcp/dcc-mcp-godot/issues/30)) ([01068f1](https://github.com/dcc-mcp/dcc-mcp-godot/commit/01068f1ce9d3224379c5b9ba839a5c955de3e2a5))

## [0.7.0](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.6.0...v0.7.0) (2026-08-28)


### Features

* harden typed Godot playtest actions ([68f01e2](https://github.com/dcc-mcp/dcc-mcp-godot/commit/68f01e2ebd324734f3ada38ec999925146089211))

## [0.6.0](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.5.1...v0.6.0) (2026-08-27)


### Features

* add Godot install lifecycle ([258f957](https://github.com/dcc-mcp/dcc-mcp-godot/commit/258f9573921f7f5ae59d20a1f397cff110e91ca4))


### Bug Fixes

* bind Godot config recovery state ([304f2f0](https://github.com/dcc-mcp/dcc-mcp-godot/commit/304f2f0a3b81483aafec1581d724678fea56ef9a))
* bind Godot filesystem mutation boundaries ([4866920](https://github.com/dcc-mcp/dcc-mcp-godot/commit/4866920170cd3f6851abc5ec96dc8740bf5412fc))
* defer Godot addon backup cleanup ([e26b93a](https://github.com/dcc-mcp/dcc-mcp-godot/commit/e26b93af63c4cf11e954e3a9bd3febd8609e9935))
* harden Godot config recovery transaction ([413b93a](https://github.com/dcc-mcp/dcc-mcp-godot/commit/413b93af215a8041781465123d3e6d16ffbecfcb))
* harden Godot config transactions ([ea29404](https://github.com/dcc-mcp/dcc-mcp-godot/commit/ea294046849a32b91cb0c008c5db4bfd82239a42))
* harden Godot install transactions ([1999e53](https://github.com/dcc-mcp/dcc-mcp-godot/commit/1999e53a9c809a386dfc238088f76c2370d26df9))
* preserve Godot transaction user data ([98a93d8](https://github.com/dcc-mcp/dcc-mcp-godot/commit/98a93d80a0673414a78557d65b1ea7d13e217a62))
* release Godot bridge reads from main affinity ([941c300](https://github.com/dcc-mcp/dcc-mcp-godot/commit/941c300f064f6f370922e26ee9a76749d7ac1d13))
* serialize Godot screenshot publication ([d579729](https://github.com/dcc-mcp/dcc-mcp-godot/commit/d5797291f82fd507aa2c0b0282c82d76cd7fff46))

## [0.5.1](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.5.0...v0.5.1) (2026-08-26)


### Bug Fixes

* keep idle Godot bridge ready ([0d9a040](https://github.com/dcc-mcp/dcc-mcp-godot/commit/0d9a0403585f6f4b4a4248a304a0a7f0eb9dc2ce))

## [0.5.0](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.4.2...v0.5.0) (2026-08-24)


### Features

* add cross-platform Godot packaging guidance ([5e7b2d2](https://github.com/dcc-mcp/dcc-mcp-godot/commit/5e7b2d25dd247e7125c89ab6d8ea12181ec7f525))


### Bug Fixes

* publish live Godot scene context ([0e7e4db](https://github.com/dcc-mcp/dcc-mcp-godot/commit/0e7e4db9c2a216889040e8ee69acb3fbfed0373a))


### Performance Improvements

* bound Godot main-thread work ([38f1749](https://github.com/dcc-mcp/dcc-mcp-godot/commit/38f1749d2507cc5480b0b9c1a4b445b8a3b3c0e0))

## [0.4.2](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.4.1...v0.4.2) (2026-08-10)


### Bug Fixes

* support imported PackedScene assets ([#11](https://github.com/dcc-mcp/dcc-mcp-godot/issues/11)) ([4e6873b](https://github.com/dcc-mcp/dcc-mcp-godot/commit/4e6873bdd68e47f65e17155c0733a55aeb539716))

## [0.4.1](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.4.0...v0.4.1) (2026-07-19)


### Documentation

* align agent workflow and branding ([759b3fd](https://github.com/dcc-mcp/dcc-mcp-godot/commit/759b3fdc4e1f8cdba48e0b6a7240b62ed5e65b5f))
* document CLI install and updates ([983e1a2](https://github.com/dcc-mcp/dcc-mcp-godot/commit/983e1a2c3a2cd3bb2d982e23451604611e6aee87))

## [0.4.0](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.3.0...v0.4.0) (2026-07-16)


### Features

* default adapter instances to dynamic ports ([#6](https://github.com/dcc-mcp/dcc-mcp-godot/issues/6)) ([17580ae](https://github.com/dcc-mcp/dcc-mcp-godot/commit/17580ae012953ce5774702a7d6efd8a726bf62da))

## [0.3.0](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.2.0...v0.3.0) (2026-07-15)


### Features

* add comprehensive Godot editor capabilities ([b24b49f](https://github.com/dcc-mcp/dcc-mcp-godot/commit/b24b49fdc07aa0c8279ffa1cca6e4afa5ba67a53))
* add reusable asset package installation ([45c5a37](https://github.com/dcc-mcp/dcc-mcp-godot/commit/45c5a3771209157534daeea90768ec5d8f880331))


### Bug Fixes

* provide display for Linux Godot smoke ([3634a3d](https://github.com/dcc-mcp/dcc-mcp-godot/commit/3634a3db3c5849e495a97c9d41f1dc94a9d01d4c))
* report live Godot bridge readiness ([0dfaf88](https://github.com/dcc-mcp/dcc-mcp-godot/commit/0dfaf8862b048580c663f84dd08e7c611f9da531))

## [0.2.0](https://github.com/dcc-mcp/dcc-mcp-godot/compare/v0.1.0...v0.2.0) (2026-07-14)


### Features

* add Godot MCP adapter and roguelike workflow ([522c2f9](https://github.com/dcc-mcp/dcc-mcp-godot/commit/522c2f97abe8369bd34c7ab2f2f6a8c606f6a8d7))


### Bug Fixes

* require graceful core bridge shutdown ([b89dd69](https://github.com/dcc-mcp/dcc-mcp-godot/commit/b89dd6953d8eaafb6c5150eb54b03215c6bc859c))

## Changelog

All notable changes to this project are documented here.
