# Events with a picture (DvE)

The game can put the picture of an event **on top of the window only in the
news window**. In the country event window it has no place for it. So:

- an event **with a picture** must be a `news_event`
- a `country_event` is text only (if you turn a `news_event` into a
  `country_event`, the picture is gone)

A `news_event` works like any other event: it can be sent to one country
only, have several options and effects.

## The picture is a "panel"

581x436 pixels: the header bar with its label, and the 557x372 photo under
it. A plain photo would end up in the top-left corner of the window.

### Without any tool

1. Open a template from `tools/panel_templates/`
   (`panel_COUNTRY_EVENT.png`, `panel_WORLD_NEWS.png`, or
   `panel_no_label.png` to write your own header text at x=58, y=19).
2. Resize/crop your photo to **557x372** and paste it with its top-left
   corner at **x=12, y=60**.
3. Save it as PNG or DDS in `gfx/event_pictures/DVE_news/`,
   for example `news_event_DVE_my_event.png`.

### With Python (needs Pillow)

    python3 tools/dve_event_panel.py photo.png "HEADER TEXT" gfx/event_pictures/DVE_news/news_event_DVE_my_event.dds

## Register it and use it

In `interface/DVE_event_panels.gfx`:

    spriteType = {
        name = "GFX_news_event_DVE_my_event"
        texturefile = "gfx/event_pictures/DVE_news/news_event_DVE_my_event.png"
    }

In the event file:

    news_event = {
        id = my_namespace.1
        title = my_namespace.1.t
        desc = my_namespace.1.d
        picture = GFX_news_event_DVE_my_event

        is_triggered_only = yes

        option = {
            name = my_namespace.1.a
            add_stability = -0.05
        }
    }

Send it to one country with `ROM = { news_event = { id = my_namespace.1 } }`,
or to everyone with `every_country = { news_event = { id = my_namespace.1 } }`.
Test it in game with the console: `event my_namespace.1`.
