;!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
;  C O C O   3   D E F I N I T I O N S
;!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
;
;  Included by every build.  The equates only matter when the
;  game is assembled with --define=COCO3; the VSYNC macro picks
;  the right "wait for the screen flip" for either build.
;
;  VSYNC: wait for the next IRQ (and, on the CoCo 3, present
;         any frame the game has just flipped to)
;
VSYNC   MACRO
        IFDEF   COCO3
        JSR     PSYNC
        ELSE
        SYNC
        ENDC
        ENDM
;
        IFDEF   COCO3
;
;  GIME registers
;
GIMIN0  EQU     $FF90           ;init 0: CoCo mode, MMU, constant page
GIMIN1  EQU     $FF91           ;init 1: task select
GIMIRQ  EQU     $FF92           ;GIME IRQ enables
GIMFRQ  EQU     $FF93           ;GIME FIRQ enables
GIMVMD  EQU     $FF98           ;video mode
GIMVRS  EQU     $FF99           ;video resolution
GIMBRD  EQU     $FF9A           ;border colour
GIMVSC  EQU     $FF9C           ;vertical scroll
GIMVOF  EQU     $FF9D           ;vertical offset (physical addr / 8)
GIMHOF  EQU     $FF9F           ;horizontal offset
GIMMMU  EQU     $FFA0           ;MMU task 0 (8 blocks of 8K)
GIMPAL  EQU     $FFB0           ;16 palette registers
SAMSLO  EQU     $FFD8           ;0.89 MHz
SAMFST  EQU     $FFD9           ;1.79 MHz
;
;  Screen layout: two 320x192x16 screens, 4 MMU blocks each.  The
;  rows match the game's own display: 0-151 view, 152-159 status
;  line, 160-191 text.
;
SCRBLK  EQU     $30             ;first block of screen 0 (screen 1 = +4)
SCRBPR  EQU     160             ;bytes per row
SCRWIN  EQU     $4000           ;CPU window onto a screen (slots 2-5)
MIRDST  EQU     SCRWIN+16       ;the 256-wide game display, centred
MMUSL5  EQU     GIMMMU+5        ;slot 5 ($A000) holds tiles and sprites
;
;  Top-down window: 13 x 7 cells of 24 pixels around the player,
;  starting 2 bytes in and 8 rows above the top of the screen
;
TDCOLS  EQU     13
TDROWS  EQU     7
TDCELS  EQU     TDCOLS*TDROWS
;
;  Engine tables and variables live in RAM around the code
;
TDCRE   EQU     $EE00           ;creature in each window cell (type+1, b7 magic)
TDITM   EQU     $EE60           ;object in each window cell (class+1)
CODEND  EQU     $EE00           ;engine code must end below here
CVTAB   EQU     $F000           ;1bpp->4bpp tables, 1K per colour
ENGRAM  EQU     $FC00           ;engine variables
NEWFRM  EQU     ENGRAM          ;game flipped its screens
FRONT   EQU     ENGRAM+1        ;GIME screen being shown (0/1)
TXANY   EQU     ENGRAM+2        ;some text line is dirty
CVCPR   EQU     ENGRAM+3        ;colour pair while building tables
ARKEY   EQU     ENGRAM+4        ;arrow held last scan (0 = none)
ARTIM   EQU     ENGRAM+5        ;jiffies until arrow repeats
TOGREQ  EQU     ENGRAM+6        ;3-D/top-down toggle key pressed
VUSEEN  EQU     ENGRAM+7        ;the game has drawn a view
KEYNOW  EQU     ENGRAM+8        ;keyboard matrix, this scan
KEYOLD  EQU     ENGRAM+16       ;keyboard matrix, last scan
TXLINE  EQU     ENGRAM+24       ;24 dirty flags, one per text line
TAGS    EQU     ENGRAM+48       ;per 1-bit buffer: frame is top-down
SCRTD   EQU     ENGRAM+50       ;per GIME screen: holds a top-down frame
SEENLV  EQU     ENGRAM+52       ;level the SEEN map belongs to (+1)
TDIDX   EQU     ENGRAM+53       ;window cell index
TDWR    EQU     ENGRAM+54       ;window row
TDWC    EQU     ENGRAM+55       ;window column
TDROW   EQU     ENGRAM+56       ;maze row of the cell
TDCOL   EQU     ENGRAM+57       ;maze column
TDCELL  EQU     ENGRAM+58       ;maze byte of the cell
TDVIS   EQU     ENGRAM+59       ;VIS byte of the cell
CLTOP   EQU     ENGRAM+60       ;first visible row of this window row
CLBOT   EQU     ENGRAM+61       ;last visible row + 1
TDBASE  EQU     ENGRAM+62       ;(2) screen addr of the cell's row 0
TDXOF   EQU     ENGRAM+64       ;byte offset of the thing in the cell
TDW     EQU     ENGRAM+65       ;width of the thing in bytes
TDCNT   EQU     ENGRAM+66       ;rows left to copy
TDSET   EQU     ENGRAM+67       ;tile block for this cell
TDMSK   EQU     ENGRAM+68       ;open-neighbour mask (rock)
TDSHD   EQU     ENGRAM+69       ;best neighbour light (rock)
TDTMP   EQU     ENGRAM+70       ;(2) scratch
TDLR    EQU     ENGRAM+72       ;line-of-sight walker row
TDLC    EQU     ENGRAM+73       ;line-of-sight walker column
TDCTR   EQU     ENGRAM+74       ;centre cell creature (xoff shift)
ENGEND  EQU     ENGRAM+80
SEEN    EQU     ENGRAM+$80      ;32x32 bits: cells seen this level
TDLIT   EQU     ENGRAM+$100     ;per window cell: b7 line of sight, b0-2 light+1
TDDST   EQU     ENGRAM+$160     ;per window cell: distance from the player
;
        ENDC
