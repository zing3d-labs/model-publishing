## Variants

Ten files cover every combination of Side A and Side B thickness and directionality. File names follow the pattern `a_[std|lite]_[dir|nondir]_b_[std|lite]_[dir|nondir].stl`.

Six of the ten are marked **reversible**. Because Side B is flipped 180° relative to Side A, a part whose two sides differ is the same object as the one with the sides swapped — just turned over. So the file listed as Lite on A and Standard on B is also your Standard-on-A, Lite-on-B part; flip it. Only the four files whose sides match are not reversible, since swapping their sides changes nothing.

| File | Side A | Side B | |
|------|--------|--------|--|
| a_std_nondir_b_std_nondir | Standard, Nondirectional | Standard, Nondirectional | |
| a_std_dir_b_std_nondir | Standard, Directional | Standard, Nondirectional | reversible |
| a_std_dir_b_std_dir | Standard, Directional | Standard, Directional | |
| a_lite_nondir_b_std_nondir | Lite, Nondirectional | Standard, Nondirectional | reversible |
| a_lite_dir_b_std_nondir | Lite, Directional | Standard, Nondirectional | reversible |
| a_lite_nondir_b_std_dir | Lite, Nondirectional | Standard, Directional | reversible |
| a_lite_dir_b_std_dir | Lite, Directional | Standard, Directional | reversible |
| a_lite_nondir_b_lite_nondir | Lite, Nondirectional | Lite, Nondirectional | |
| a_lite_dir_b_lite_nondir | Lite, Directional | Lite, Nondirectional | reversible |
| a_lite_dir_b_lite_dir | Lite, Directional | Lite, Directional | |
