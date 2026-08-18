// Test fixture used only to rehearse the MakerWorld publish/update automation.
// Not a real product — safe to publish as a private/throwaway listing.

/* [Dimensions] */
// Width of the box (mm)
Width = 20; // [10:5:100]
// Depth of the box (mm)
Depth = 20; // [10:5:100]
// Height of the box (mm)
Height = 10; // [5:5:50]

/* [Corner] */
// Rounded corner radius (mm). 0 disables rounding.
Corner_Radius = 3; // [0:1:10]

// Marker section for the 2026-08-09 --scad delete+reupload test: a brand new
// parameter group is the only unambiguous signal that the raw .scad on
// MakerWorld was really replaced. Defaults to 0 so the default geometry (and
// therefore the .3mf) is unchanged, isolating the customizer-source path.
/* [Lid] */
// Thickness of a solid lid on top (mm). 0 disables the lid.
Lid_Thickness = 0; // [0:1:10]

module rounded_box(w, d, h, r) {
    if (r <= 0) {
        cube([w, d, h]);
    } else {
        hull() {
            for (x = [r, w - r])
                for (y = [r, d - r])
                    translate([x, y, 0])
                        cylinder(r = r, h = h, $fn = 32);
        }
    }
}

rounded_box(Width, Depth, Height, Corner_Radius);

if (Lid_Thickness > 0)
    translate([0, 0, Height])
        rounded_box(Width, Depth, Lid_Thickness, Corner_Radius);
