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
