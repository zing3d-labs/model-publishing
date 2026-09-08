## Sizes

Every plate is built around a sheet size, and the 28mm openGrid tile does the rest — the panels snap to whole tiles so the openConnect slot grid reaches the panel edges with nothing left over.

- **US Letter** — 224 × 89 × 224mm, a full 8 × 8 tile grid, 219.2mm pocket, 126mm of the sheet visible above the front panel
- **A4** — 224 × 91 × 224mm, 8 × 8 tiles, 219.2mm pocket, 134mm visible
- **A5** — 168 × 81 × 168mm, 6 × 6 tiles, 163.2mm pocket, 95mm visible

US Letter and A4 come out the same width and the same height — the tile snap absorbs the difference — so either one holds both sheet sizes. What actually changes between them is how tall the front panel stands, and so how much of the page you can read at a glance.

The pocket is 50mm deep at the floor, which is about a full ream of paper.

## Perforation

The front and side panels are cut with a hex honeycomb by default. It takes roughly a quarter of the material out of the part — 229cm³ instead of 306cm³ at US Letter — and a good deal of the print time with it. A square lattice and a fully solid version are on their own plates if you prefer one of those.

The back panel is always left solid — it is what carries the mount.

Holes never land on a corner or a seam. The 8mm border is measured not just from each panel's outer edges but from every joint the panel makes: the pocket floor, the neighbouring panels, the finger cutout, and the slot grid. Cells that would have been sliced into unprintably thin slivers along the side panels' taper are removed rather than left as fragments.

## What You Need

- An openGrid wall, board, or desk mount — Full or Lite, either works
- A few openConnect snaps. **This model has the slots, not the connectors** — print the snaps from mitufy's openConnect model, linked at the bottom. You only need one per grid position you actually want to use, not all 64.

## Customizing

The `.scad` source is attached, so the MakerWorld customizer exposes the whole design: paper size (including Custom dimensions and a Landscape option), pocket depth, rake angle, panel heights and thicknesses, the finger cutout style, and every perforation and mount setting.

One thing worth knowing if you open the file in OpenSCAD yourself: at the default 8 × 8 grid the back panel carries 64 openConnect slots, which is more than OpenSCAD's preview can flatten. **F5 shows an empty preview** and warns that CSG normalization was aborted. That is a limit in the preview pipeline, not a problem with the part — **F6 renders correctly**, and so does every exported file and every plate in this download. Lowering `Mount_Vertical_Grids`, or setting `Slot_Position` to something sparser than "All", brings F5 back if you want it.
