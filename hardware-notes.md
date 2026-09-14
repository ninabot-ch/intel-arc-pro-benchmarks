# Which motherboards actually take 4 double-width Arc Pro cards

Arc Pro B60 and B70 blower cards are **2 slots thick**. Four of them need four slots
each with a free neighbour. That is a mechanical constraint, and it eliminates most
server boards — including several that advertise enough x16 slots.

We measured slot pitch directly from vendor layout drawings in the manuals (vector
PDFs, scaled against the board dimension printed on the same drawing). Method and
numbers below so you can check them.

## Results

| Board | Socket | Slots | Pitch | Double-width cards | Bracket positions needed |
|---|---|---|---|---|---|
| Supermicro H13SSL-N | SP5 | 3× x16 + 2× x8, consecutive | 20.05 mm | **3** | — |
| Supermicro H12SSL-i | SP3 | 5× x16 + 2× x8 | — | **3** | — |
| ASRock Rack ROMED8-2T | SP3 | 7× x16, consecutive | 20.05 mm | **4** | 8 |
| ASRock Rack GENOAD8X-2T/BCM | SP5 | 7× x16 + 1× x8, consecutive | 20.2 mm | **4** | **9** |
| ASUS Pro WS WRX90E-SAGE SE | sTR5 | 7× x16 | 20.3 mm | **4** | 8 |
| ASUS Pro WS W790E-SAGE SE | LGA4677 | 7× x16 | 20.7 mm | **4** | 8 |

## The distinction that matters

**Server boards stack their slots at single pitch, consecutively.** That is deliberate:
they assume GPUs arrive on a riser backplane, not plugged into the board. So a board
with five or seven x16 slots still only takes three double-width cards.

**Workstation boards space theirs for double-width cards.** ASUS documents this
explicitly for the SAGE boards — their manual's "Recommended VGA configuration" table
gives **4-Way VGA = slots 1, 3, 5, 7**, which fits four 2-slot cards inside 8 bracket
positions. That is what makes them work in a standard 4U chassis.

The GENOAD8X is the trap in the list: it genuinely takes four double-width cards, but
its eight consecutive slots push the fourth card's cooler into a **ninth** bracket
position. A 4U chassis has room for eight (177.8 mm ÷ 20.32 mm). So it is a tower-only
board, despite being a server board.

## Details worth knowing

**ASUS Pro WS WRX90E-SAGE SE** — sTR5, EEB, 7× PCIe 5.0 x16, 128 Gen5 lanes, ASPEED
AST2600 BMC with dedicated IPMI LAN, 8× DDR5 RDIMM ECC, dual 10 GbE, x4x4x4x4
bifurcation on six slots. The manual also notes: *"When installing a dual VGA card, we
recommend selecting a chassis case which supports 7 or more expansion slots."* The
`PCIE_8P_PWR` connectors must be cabled with two or more GPUs, or the BIOS blocks.

**ASUS Pro WS W790E-SAGE SE** — the Intel equivalent, same 7-slot layout. Note the CPU
split: with a **Xeon W-3400** all seven slots are active (x16/x16/x16/x16/x16/x8/x16);
with a **W-2400** only slots **1, 3, 5, 7** are active at x16 — which happens to be
exactly the four double-width positions, at a much lower CPU price. The trade is 4
memory channels instead of 8.

**ASRock Rack GENOAD8X-2T/BCM** — SP5, EEB 12.63" × 13", 7× x16 + 1× x8 (the x8 is
physically short and closed-ended, so a x16-edge card will not fit it), 8 DDR5 slots
only, so 8 of the SP5's 12 memory channels. Phison PS7101 redrivers across the slot
array.

**Arc Pro card widths.** B60 Creator and B70 are 2-slot blowers. The **ASRock B60
Passive is 1 slot** — seven of those fit seven slots on any of the 7-slot boards above,
but passive cards need real front-to-back server airflow and will not work in a quiet
tower. The B70 Passive is 2 slots (39 mm).

## Method

Render the layout page of the vendor manual from the PDF at known DPI, measure the
pixel distance between slot connector centres, and scale using the board dimension
printed on the same drawing. Example, GENOAD8X-2T/BCM: board is 32.08 cm along the
rear-panel edge and spans 573 px at 150 DPI → 1.786 px/mm; slots are 36.2 px apart →
20.3 mm. Standard ATX slot pitch is 20.32 mm, so the slots are consecutive with no gap.

This is worth doing yourself rather than trusting a spec sheet: three of the boards in
the table advertise enough x16 slots for four GPUs and cannot physically hold them.
