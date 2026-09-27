from ezdxf import bbox

from shipdraw.bom import Bom, BomRow
from shipdraw.render.bom_table import COLUMNS, bom_cells, draw_bom_table
from shipdraw.render.sheet import new_document

BOM = Bom(
    (
        BomRow(1, "PL 8 AH36 (9000 x 3500)", 1, None, 1927.332),
        BomRow(2, "HP 160x8", 12, 3500.0, 520.8),
        BomRow(3, "HP 160x8", 2, 3200.0, 79.36),
        BomRow(4, "BKT 250x250x8", 28, None, 53.8004),
    )
)


def test_bom_cells():
    cells = bom_cells(BOM)
    assert cells[0] == ("ITEM", "DESCRIPTION", "QTY", "LENGTH (mm)", "WEIGHT (kg)")
    assert cells[1] == ("1", "PL 8 AH36 (9000 x 3500)", "1", "-", "1927.3")
    assert cells[2] == ("2", "HP 160x8", "12", "3500", "520.8")
    assert cells[-1] == ("", "TOTAL", "", "", "2581.3")
    assert len(cells) == 6


def test_table_grid_and_text(standard, example_plan):
    msp = new_document(standard, example_plan.scale).modelspace()
    draw_bom_table(msp, BOM, standard, example_plan)
    layer = standard.layers.bom.name
    assert len(msp.query(f'LINE[layer=="{layer}"]')) == (6 + 1) + (len(COLUMNS) + 1)
    texts = [t.dxf.text for t in msp.query(f'TEXT[layer=="{layer}"]')]
    assert {"BILL OF MATERIALS", "TOTAL", "2581.3", "PL 8 AH36 (9000 x 3500)"} <= set(texts)
    assert all(e.dxf.layer == layer for e in msp)


def test_table_stays_inside_the_bom_zone(standard, example_plan):
    msp = new_document(standard, example_plan.scale).modelspace()
    draw_bom_table(msp, BOM, standard, example_plan)
    box = bbox.extents(msp)
    zone, s = standard.sheet.zones.bom, example_plan.scale
    assert box.extmin.x >= zone.x * s and box.extmin.y >= zone.y * s
    assert box.extmax.x <= (zone.x + zone.width) * s and box.extmax.y <= (zone.y + zone.height) * s
