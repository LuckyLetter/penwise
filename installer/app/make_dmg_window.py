"""Write how the Penwise disk image's window looks when it opens, installer/app/dmg.DS_Store (put in
the disk image as .DS_Store): big icons, Penwise on the left and Applications on the right to drag
it onto, with no toolbar or sidebar. As dmgbuild writes it. Run it again only to change the window:

    uv run --no-project --with ds_store python installer/app/make_dmg_window.py
"""

from pathlib import Path

from ds_store import DSStore

WIDTH, HEIGHT = 540, 360

if __name__ == "__main__":
    path = Path(__file__).with_name("dmg.DS_Store")
    path.unlink(missing_ok=True)
    with DSStore.open(str(path), "w+") as store:
        store["."]["vSrn"] = ("long", 1)
        store["."]["bwsp"] = {
            "WindowBounds": f"{{{{200, 120}}, {{{WIDTH}, {HEIGHT}}}}}",
            "ShowStatusBar": False,
            "ShowToolbar": False,
            "ShowPathbar": False,
            "ShowSidebar": False,
            "ShowTabView": False,
            "ContainerShowSidebar": False,
            "PreviewPaneVisibility": False,
            "SidebarWidth": 0,
        }
        store["."]["icvp"] = {
            "viewOptionsVersion": 1,
            "backgroundType": 0,
            "backgroundColorRed": 1.0,
            "backgroundColorGreen": 1.0,
            "backgroundColorBlue": 1.0,
            "gridOffsetX": 0.0,
            "gridOffsetY": 0.0,
            "gridSpacing": 100.0,
            "arrangeBy": "none",
            "showIconPreview": False,
            "showItemInfo": False,
            "labelOnBottom": True,
            "textSize": 13.0,
            "iconSize": 128.0,
            "scrollPositionX": 0.0,
            "scrollPositionY": 0.0,
        }
        store["."]["icvl"] = ("type", b"icnv")  # icon view
        store["Penwise.app"]["Iloc"] = (140, 165)
        store["Applications"]["Iloc"] = (400, 165)
    print(path)
