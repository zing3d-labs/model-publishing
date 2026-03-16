#!/usr/bin/env python3
from solid import *

scadfile = import_scad('./kits/grid_basket/scratch.scad')

bosl2 = import_scad('BOSL2')
local = import_scad('./')
print(dir(bosl2))
print("\nhere\n")

print(scadfile)

