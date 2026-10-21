// SPDX-License-Identifier: GPL-2.0
// PF818 M08 panel: timings and DCS commands from the running factory DT.
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/module.h>
#include <linux/of.h>

#include <drm/drm_connector.h>
#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>

#include "factory_init.h"

struct pf818_panel {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi;
	struct gpio_desc *enable;
	struct gpio_desc *reset;
};

static struct pf818_panel *to_pf818(struct drm_panel *panel)
{
	return container_of(panel, struct pf818_panel, panel);
}

static int pf818_prepare(struct drm_panel *panel)
{
	struct pf818_panel *ctx = to_pf818(panel);
	size_t pos = 0;
	int ret;

	gpiod_set_value_cansleep(ctx->enable, 1);
	gpiod_set_value_cansleep(ctx->reset, 1);
	msleep(10);
	gpiod_set_value_cansleep(ctx->reset, 0);
	msleep(10);

	/* Factory records: packet type, post-command delay, length, DCS bytes.
	 * M08 uses only DCS short writes (0x15 and 0x05), inferred by length.
	 */
	while (pos < sizeof(pf818_factory_init)) {
		u8 delay = pf818_factory_init[pos + 1];
		u8 len = pf818_factory_init[pos + 2];

		ret = mipi_dsi_dcs_write_buffer(ctx->dsi,
					      pf818_factory_init + pos + 3, len);
		if (ret < 0) {
			dev_err(panel->dev, "DCS command at %zu failed: %d\n", pos, ret);
			gpiod_set_value_cansleep(ctx->reset, 1);
			gpiod_set_value_cansleep(ctx->enable, 0);
			return ret;
		}
		if (delay)
			msleep(delay);
		pos += 3 + len;
	}
	dev_info(panel->dev, "factory M08 sequence complete, 1200x1920\n");
	return 0;
}

static int pf818_unprepare(struct drm_panel *panel)
{
	struct pf818_panel *ctx = to_pf818(panel);

	mipi_dsi_dcs_set_display_off(ctx->dsi);
	msleep(20);
	mipi_dsi_dcs_enter_sleep_mode(ctx->dsi);
	msleep(120);
	gpiod_set_value_cansleep(ctx->reset, 1);
	gpiod_set_value_cansleep(ctx->enable, 0);
	return 0;
}

static const struct drm_display_mode pf818_mode = {
	.clock = 154500,
	.hdisplay = 1200,
	.hsync_start = 1200 + 62,
	.hsync_end = 1200 + 62 + 4,
	.htotal = 1200 + 62 + 4 + 62,
	.vdisplay = 1920,
	.vsync_start = 1920 + 8,
	.vsync_end = 1920 + 8 + 2,
	.vtotal = 1920 + 8 + 2 + 9,
	.flags = DRM_MODE_FLAG_NHSYNC | DRM_MODE_FLAG_NVSYNC,
};

static int pf818_get_modes(struct drm_panel *panel, struct drm_connector *connector)
{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, &pf818_mode);
	if (!mode)
		return -ENOMEM;
	drm_mode_set_name(mode);
	mode->type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED;
	drm_mode_probed_add(connector, mode);
	connector->display_info.bpc = 8;
	return 1;
}

static const struct drm_panel_funcs pf818_funcs = {
	.prepare = pf818_prepare,
	.unprepare = pf818_unprepare,
	.get_modes = pf818_get_modes,
};

static int pf818_probe(struct mipi_dsi_device *dsi)
{
	struct device *dev = &dsi->dev;
	struct pf818_panel *ctx;
	int ret;

	ctx = devm_drm_panel_alloc(dev, struct pf818_panel, panel,
				   &pf818_funcs, DRM_MODE_CONNECTOR_DSI);
	if (IS_ERR(ctx))
		return PTR_ERR(ctx);
	ctx->dsi = dsi;
	ctx->enable = devm_gpiod_get(dev, "enable", GPIOD_OUT_LOW);
	if (IS_ERR(ctx->enable))
		return dev_err_probe(dev, PTR_ERR(ctx->enable), "enable GPIO\n");
	ctx->reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(ctx->reset))
		return dev_err_probe(dev, PTR_ERR(ctx->reset), "reset GPIO\n");
	ret = drm_panel_of_backlight(&ctx->panel);
	if (ret)
		return dev_err_probe(dev, ret, "backlight\n");

	dsi->lanes = 4;
	dsi->format = MIPI_DSI_FMT_RGB888;
	/* Vendor 4.4 flag 0x200 enabled EoT; current kernels enable it by default. */
	dsi->mode_flags = MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST |
			  MIPI_DSI_MODE_LPM;
	mipi_dsi_set_drvdata(dsi, ctx);
	drm_panel_add(&ctx->panel);
	ret = mipi_dsi_attach(dsi);
	if (ret) {
		drm_panel_remove(&ctx->panel);
		return dev_err_probe(dev, ret, "DSI attach\n");
	}
	return 0;
}

static void pf818_remove(struct mipi_dsi_device *dsi)
{
	struct pf818_panel *ctx = mipi_dsi_get_drvdata(dsi);

	drm_panel_disable(&ctx->panel);
	drm_panel_unprepare(&ctx->panel);
	mipi_dsi_detach(dsi);
	drm_panel_remove(&ctx->panel);
}

static void pf818_shutdown(struct mipi_dsi_device *dsi)
{
	struct pf818_panel *ctx = mipi_dsi_get_drvdata(dsi);

	drm_panel_disable(&ctx->panel);
	drm_panel_unprepare(&ctx->panel);
}

static const struct of_device_id pf818_of_match[] = {
	{ .compatible = "bozztek,pf818-m08" },
	{ }
};
MODULE_DEVICE_TABLE(of, pf818_of_match);

static struct mipi_dsi_driver pf818_driver = {
	.probe = pf818_probe,
	.remove = pf818_remove,
	.shutdown = pf818_shutdown,
	.driver = {
		.name = "panel-pf818",
		.of_match_table = pf818_of_match,
	},
};
module_mipi_dsi_driver(pf818_driver);

MODULE_DESCRIPTION("Bozztek PF818 factory M08 DSI panel");
MODULE_LICENSE("GPL");
