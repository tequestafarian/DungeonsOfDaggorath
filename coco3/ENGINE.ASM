;!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
;  C O C O   3   E N G I N E
;!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
;
;  Runs the game on the GIME's 320x192 16-colour screen, in one of
;  two views (F1 or CLEAR switches between them):
;
;  3-D       The game draws its usual 1-bit view; when it flips
;            buffers the engine converts the new one to colour.
;  Top-down  VIEWER is replaced by TDVIEW, which draws the maze from
;            above straight into the hidden colour screen, using
;            tiles and sprites kept in the upper 512K (see
;            tools/topdown/make_assets.py).  The status line and
;            text are still the game's, converted from its buffer.
;
;  Every 1-bit buffer carries a tag saying whether its frame was a
;  top-down one, so the map, EXAMINE, PREPARE! and the wizard always
;  come through as they were drawn.
;
;  The keyboard is scanned here too (BASIC's POLCAT is gone): the
;  arrow keys type MOVE, MOVE BACK, TURN LEFT and TURN RIGHT.
;
        INCLUDE ../build/TDTAB.ASM
;
TOPDN   FCB     $FF             ;top-down view on (kept across restarts)
;
;
;  ENGINI: GIME setup (called from COMINI on every restart)
;
ENGINI  PSHS    A,B,X,Y,U       ;save regs
        STA     SAMFST          ;1.79 MHz
        LDA     #$4C            ;CoCo 3 mode, MMU on, constant $FExx
        STA     GIMIN0          ;   .
        CLR     GIMIN1          ;task 0
        CLR     GIMIRQ          ;no GIME interrupts
        CLR     GIMFRQ          ;   .
        LDD     #$801E          ;graphics, 192 lines, 160 bytes, 16 colours
        STD     GIMVMD          ;   .
        CLR     GIMBRD          ;black border
        CLR     GIMVSC          ;   .
        CLR     GIMHOF          ;   .
;
        LDX     #TDPAL          ;load the palette
        LDU     #GIMPAL         ;   .
ENI10   LDA     ,X+             ;   .
        STA     ,U+             ;   .
        CMPU    #GIMPAL+16      ;   .
        BLO     ENI10           ;   .
;
;  Build the 1bpp->4bpp tables.  For colour pair C and source byte
;  B, table byte (k*256)+B holds pixels 2k and 2k+1 in colour C.
;
        LDU     #CVTAB          ;first colour's tables
        LDX     #CVCOLS         ;colour pairs
ENI20   LDA     ,X+             ;next colour pair
        BEQ     ENI40           ;   done
        STA     CVCPR           ;   .
        TFR     U,Y             ;Y walks the source bytes
ENI30   TFR     Y,D             ;B <- source byte
        LBSR    PIXPR           ;bits 1-0
        STA     $300,Y          ;   .
        LSRB                    ;bits 3-2
        LSRB                    ;   .
        LBSR    PIXPR           ;   .
        STA     $200,Y          ;   .
        LSRB                    ;bits 5-4
        LSRB                    ;   .
        LBSR    PIXPR           ;   .
        STA     $100,Y          ;   .
        LSRB                    ;bits 7-6
        LSRB                    ;   .
        LBSR    PIXPR           ;   .
        STA     ,Y+             ;   .
        TFR     Y,D             ;end of page?
        TSTB                    ;   .
        BNE     ENI30           ;   nope
        LEAU    $400,U          ;next colour's tables
        BRA     ENI20           ;   .
;
;  Clear both screens and show screen 0
;
ENI40   CLRA                    ;screen 0
ENI50   LBSR    MAPWIN          ;map it into the window
        PSHS    A               ;   .
        LDX     #SCRWIN         ;   .
        LDD     #0              ;   .
ENI52   STD     ,X++            ;   .
        CMPX    #SCRWIN+$8000   ;   .
        BNE     ENI52           ;   .
        PULS    A               ;   .
        INCA                    ;next screen
        CMPA    #2              ;   .
        BLO     ENI50           ;   .
;
        LDX     #ENGRAM         ;zero the engine variables
ENI60   CLR     ,X+             ;   .
        CMPX    #ENGEND         ;   .
        BLO     ENI60           ;   .
        CLRA                    ;show screen 0
        LBSR    SHOWSC          ;   .
        PULS    A,B,X,Y,U,PC    ;restore regs/exit
;
;  PIXPR: two 1-bit pixels (B bits 1-0) -> one 4bpp byte in CVCPR
;
PIXPR   PSHS    B,X             ;save regs
        ANDB    #3              ;   .
        LDX     #PIXMSK         ;   .
        LDA     B,X             ;   .
        ANDA    CVCPR           ;   .
        PULS    B,X,PC          ;   .
;
PIXMSK  FCB     $00,$0F,$F0,$FF
CVCOLS  FCB     $FF,$77,$DD,0   ;view white, status gold, text cyan
;
;  MAPWIN: map all of screen A (0/1) into the CPU window $4000-$BFFF
;  MAPPF:  map rows 0-153 of screen A into $4000-$9FFF, leaving
;          slot 5 ($A000) for tiles and sprites
;
MAPWIN  PSHS    A,X             ;save regs
        LBSR    MAPSUB          ;first three blocks
        INCA                    ;fourth
        STA     ,X              ;   .
        PULS    A,X,PC          ;restore regs/exit
;
MAPPF   PSHS    A,X             ;save regs
        LBSR    MAPSUB          ;   .
        PULS    A,X,PC          ;restore regs/exit
;
MAPSUB  LSLA                    ;block = SCRBLK + 4*A
        LSLA                    ;   .
        ADDA    #SCRBLK         ;   .
        LDX     #GIMMMU+2       ;slots 2-4
        STA     ,X+             ;   .
        INCA                    ;   .
        STA     ,X+             ;   .
        INCA                    ;   .
        STA     ,X+             ;   .
        RTS
;
;  SHOWSC: display screen A (0/1)
;
SHOWSC  PSHS    A               ;save regs
        STA     FRONT           ;   .
        LSLA                    ;(SCRBLK + 4*A) * $2000 / 8
        LSLA                    ;   .
        ADDA    #SCRBLK         ;   .
        LSLA                    ;   .
        LSLA                    ;   .
        STA     GIMVOF          ;   .
        CLR     GIMVOF+1        ;   .
        PULS    A,PC            ;restore regs/exit
;
;  CVROWS: convert 1bpp rows to 4bpp
;
;  Inputs:
;       A - page of the colour's tables
;       B - number of rows (32 source bytes each)
;       X - source (advanced)
;       U - destination in the window (advanced a full row each)
;
CVROWS  STA     CVR15+1         ;patch the table page
        PSHS    B               ;row count
CVR10   LDB     #32             ;bytes per row
        PSHS    B               ;   .
CVR12   LDB     ,X+             ;next 8 pixels
        BEQ     CVR20           ;   all black
CVR15   LDA     #0              ;table page (patched)
        TFR     D,Y             ;   .
        LDA     ,Y              ;pixels 0-1
        LDB     $100,Y          ;pixels 2-3
        STD     ,U++            ;   .
        LDA     $200,Y          ;pixels 4-5
        LDB     $300,Y          ;pixels 6-7
        STD     ,U++            ;   .
        DEC     ,S              ;   .
        BNE     CVR12           ;   .
        BRA     CVR30           ;   .
CVR20   CLRA                    ;D <- 0
        STD     ,U++            ;   .
        STD     ,U++            ;   .
        DEC     ,S              ;   .
        BNE     CVR12           ;   .
CVR30   LEAS    1,S             ;   .
        LEAU    SCRBPR-128,U    ;skip the side borders
        DEC     ,S              ;   .
        BNE     CVR10           ;   .
        PULS    B,PC            ;   .
;
;  PRESNT: show the frame the game just flipped to, on the hidden
;          GIME screen.  A top-down frame is already drawn there and
;          only needs its status line and text.
;
PRESNT  PSHS    A,B,X,Y,U       ;save regs
        CLR     NEWFRM          ;   .
        LBSR    TXCLR           ;the whole screen is fresh
        LDA     FRONT           ;draw on the other screen
        EORA    #1              ;   .
        PSHS    A               ;   .
        LBSR    MAPWIN          ;   .
        LDU     FLIP            ;game's displayed buffer
        LBSR    TAGPTR          ;top-down frame?
        LDB     ,S              ;   (B = screen)
        LDY     #SCRTD          ;   .
        TST     ,X              ;   .
        BEQ     PRE20           ;   nope - convert all of it
;
        LDA     #1              ;screen holds a top-down frame
        STA     B,Y             ;   .
        LDX     P.VDBAS,U       ;status line and text only
        LEAX    152*32,X        ;   .
        LDU     #MIRDST+(152*SCRBPR)
        BRA     PRE30           ;   .
;
PRE20   TST     B,Y             ;last frame here top-down?
        BEQ     PRE24           ;   nope
        CLR     B,Y             ;   .
        LDX     #SCRWIN         ;clear the playfield's side borders
        LDD     #0              ;   .
PRE22   STD     ,X              ;   .
        STD     2,X             ;   .
        STD     4,X             ;   .
        STD     6,X             ;   .
        STD     8,X             ;   .
        STD     10,X            ;   .
        STD     12,X            ;   .
        STD     14,X            ;   .
        STD     144,X           ;   .
        STD     146,X           ;   .
        STD     148,X           ;   .
        STD     150,X           ;   .
        STD     152,X           ;   .
        STD     154,X           ;   .
        STD     156,X           ;   .
        STD     158,X           ;   .
        LEAX    SCRBPR,X        ;   .
        CMPX    #SCRWIN+(152*SCRBPR)
        BLO     PRE22           ;   .
PRE24   LDX     P.VDBAS,U       ;view
        LDU     #MIRDST         ;   .
        LDA     #CVTAB/256      ;   .
        LDB     #152            ;   .
        LBSR    CVROWS          ;   .
PRE30   LDA     #CVTAB/256+4    ;status line
        LDB     #8              ;   .
        LBSR    CVROWS          ;   .
        LDA     #CVTAB/256+8    ;text lines
        LDB     #32             ;   .
        LBSR    CVROWS          ;   .
        PULS    A               ;show it
        LBSR    SHOWSC          ;   .
        PULS    A,B,X,Y,U,PC    ;restore regs/exit
;
;  TAGPTR: X <- addr of the top-down tag of the buffer in VDB U
;
TAGPTR  PSHS    A               ;save regs
        LDX     #TAGS           ;   .
        LDA     P.VDBAS,U       ;   .
        CMPA    #D1$BAS/256     ;   .
        BLO     TAG10           ;   .
        LEAX    1,X             ;   .
TAG10   PULS    A,PC            ;   .
;
;  TDUNTG: the buffer in VDB U was cleared for something else
;          (called from ZFLIP/ZFLOP)
;  TDUNTF: the same for FLOP (called from MAPPER, which doesn't clear)
;
TDUNTF  PSHS    U               ;save regs
        LDU     FLOP            ;   .
        LBSR    TDUNTG          ;   .
        PULS    U,PC            ;   .
;
TDUNTG  PSHS    X               ;save regs
        LBSR    TAGPTR          ;   .
        CLR     ,X              ;   .
        PULS    X,PC            ;   .
;
;  TXCLR: forget all dirty text lines
;
TXCLR   PSHS    X               ;save regs
        CLR     TXANY           ;   .
        LDX     #TXLINE         ;   .
TXC10   CLR     ,X+             ;   .
        CMPX    #TXLINE+24      ;   .
        BLO     TXC10           ;   .
        PULS    X,PC            ;   .
;
;  TXMARK: note that text was deposited (called from TXTDPB)
;
;  Inputs:
;       Y - display addr in either 1-bit buffer
;
TXMARK  PSHS    A,B,X           ;save regs
        TFR     Y,D             ;line = (Y - buffer base) / 256
        CMPA    #D1$BAS/256     ;   .
        BLO     TXM10           ;   .
        SUBA    #(D1$BAS-D0$BAS)/256
TXM10   SUBA    #D0$BAS/256     ;   .
        CMPA    #24             ;   .
        BHS     TXM90           ;   not a display addr
        LDX     #TXLINE         ;   .
        LDB     #1              ;   .
        STB     A,X             ;   .
        STB     TXANY           ;   .
TXM90   PULS    A,B,X,PC        ;restore regs/exit
;
;  TXSMRK: note that a text window scrolled (called from TXTSCR)
;
;  Inputs:
;       U - ptr to TXB
;       X - end of the window
;
TXSMRK  PSHS    Y               ;save regs
        LDY     P.TXBAS,U       ;every line of the window
TXS10   JSR     TXMARK          ;   .
        LEAY    256,Y           ;   .
        PSHS    X               ;   .
        CMPY    ,S++            ;   .
        BLO     TXS10           ;   .
        PULS    Y,PC            ;restore regs/exit
;
;  PSYNC: the game's "wait for the flip"
;
PSYNC   SYNC                    ;wait for the IRQ
        BRA     ENGIDL          ;   .
;
;  ENGSCH: called from SCHED between tasks - the one place where it
;          is safe to have the game redraw the view after F1
;
ENGSCH  TST     TOGREQ          ;switch views?
        BEQ     ENGIDL          ;   nope
        CLR     TOGREQ          ;   .
        COM     TOPDN           ;   .
        TST     VUSEEN          ;is there a view to redraw?
        BEQ     ENGIDL          ;   not yet
        LDX     DSPMOD          ;   .
        CMPX    #VIEWER         ;   .
        BNE     ENGIDL          ;   map or EXAMINE is up
        SWI                     ;redraw it
        FCB     PUPDAT          ;   .
;
;  ENGIDL: present new frames and dirty text
;
ENGIDL  PSHS    A,B,X,Y,U       ;save regs
        TST     NEWFRM          ;did the game flip?
        BEQ     EID10           ;   nope
        LBSR    PRESNT          ;   .
EID10   TST     TXANY           ;any text to show?
        BEQ     EID90           ;   nope
        CLR     TXANY           ;   .
        LDA     FRONT           ;straight onto the visible screen
        LBSR    MAPWIN          ;   .
        CLRB                    ;line number
EID20   LDX     #TXLINE         ;dirty?
        TST     B,X             ;   .
        BEQ     EID30           ;   nope
        CLR     B,X             ;   .
        CMPB    #19             ;in the view area of a top-down screen?
        BHS     EID22           ;   nope
        LDX     #SCRTD          ;   .
        LDA     FRONT           ;   .
        TST     A,X             ;   .
        BNE     EID30           ;   yes - leave the playfield alone
EID22   PSHS    B               ;   .
        LDX     FLIP            ;source = buffer + line*256
        LDD     P.VDBAS,X       ;   .
        ADDA    ,S              ;   .
        TFR     D,X             ;   .
        LDA     ,S              ;dest = MIRDST + line*8*160
        LDB     #5              ;   .
        MUL                     ;   .
        TFR     B,A             ;   .
        CLRB                    ;   .
        ADDD    #MIRDST         ;   .
        TFR     D,U             ;   .
        LDB     ,S              ;colour by region
        LDA     #CVTAB/256      ;   view
        CMPB    #19             ;   .
        BLO     EID25           ;   .
        LDA     #CVTAB/256+4    ;   status line
        CMPB    #19             ;   .
        BEQ     EID25           ;   .
        LDA     #CVTAB/256+8    ;   text
EID25   LDB     #8              ;one text line
        LBSR    CVROWS          ;   .
        PULS    B               ;   .
EID30   INCB                    ;next line
        CMPB    #24             ;   .
        BLO     EID20           ;   .
EID90   PULS    A,B,X,Y,U,PC    ;restore regs/exit
;
;  KEYSCN: scan the keyboard (called from CLOCK, DP = $02)
;
KEYSCN  LDX     #KEYNOW         ;read all 8 columns
        LDB     #%11111110      ;   .
KSN10   STB     P.PIIOB+PIA$0   ;   .
        LDA     P.PIIOA+PIA$0   ;   .
        COMA                    ;1 = pressed
        ANDA    #$7F            ;   .
        STA     ,X+             ;   .
        ORCC    #CC.C           ;next column
        ROLB                    ;   .
        CMPB    #$FF            ;   .
        BNE     KSN10           ;   .
        STB     P.PIIOB+PIA$0   ;   .
;
;  New key presses become characters
;
        LDY     #KEYMAP         ;column 0
        LDX     #KEYNOW         ;   .
KSN20   LDA     8,X             ;newly pressed = now & ~old
        COMA                    ;   .
        ANDA    ,X              ;   .
        LDB     ,X+             ;old <- now
        STB     7,X             ;   .
        PSHS    Y               ;   .
KSN22   LSRA                    ;next row
        BCC     KSN26           ;   not pressed
        PSHS    A               ;   .
        LDA     ,Y              ;   .
        BEQ     KSN24           ;   no character
        BPL     KSN23           ;   .
        STA     TOGREQ          ;F1/CLEAR: switch views
        BRA     KSN24           ;   .
KSN23   JSR     KBDPUT          ;   .
KSN24   PULS    A               ;   .
KSN26   LEAY    8,Y             ;   .
        TSTA                    ;   .
        BNE     KSN22           ;   .
        PULS    Y               ;   .
        LEAY    1,Y             ;next column
        CMPX    #KEYNOW+8       ;   .
        BLO     KSN20           ;   .
;
;  Arrow keys: fire on press, then repeat while held
;
        LDB     #1              ;up, down, left, right = 1-4
        LDX     #KEYNOW+3       ;   (row 3, columns 3-6)
KSN30   LDA     ,X+             ;   .
        BITA    #%00001000      ;   .
        BNE     KSN32           ;   held
        INCB                    ;   .
        CMPB    #5              ;   .
        BLO     KSN30           ;   .
        CLRB                    ;none held
KSN32   CMPB    ARKEY           ;same as last time?
        BEQ     KSN34           ;   yes
        STB     ARKEY           ;   .
        BEQ     KSN99           ;   released
        LDA     #ARPT1          ;first repeat delay
        BRA     KSN36           ;   .
KSN34   TSTB                    ;   .
        BEQ     KSN99           ;   .
        DEC     ARTIM           ;   .
        BNE     KSN99           ;   .
        LDA     #ARPT2          ;   .
KSN36   STA     ARTIM           ;   .
;
;  Fire arrow B: type its command if the line is empty, otherwise
;  the left arrow is a backspace
;
        LDX     LINPTR          ;anything typed?
        CMPX    #LINBUF         ;   .
        BNE     KSN50           ;   yes
        LDA     KBDHDR          ;keys still waiting?
        CMPA    KBDTAL          ;   .
        BNE     KSN99           ;   yes - let them go first
        LSLB                    ;   .
        LDX     #ARCMDS-2       ;   .
        LDX     B,X             ;   .
KSN40   LDA     ,X+             ;type the command
        BEQ     KSN99           ;   .
        JSR     KBDPUT          ;   .
        BRA     KSN40           ;   .
KSN50   CMPB    #3              ;left?
        BNE     KSN99           ;   nope
        LDA     #C.BS           ;   .
        JSR     KBDPUT          ;   .
KSN99   RTS
;
ARPT1   EQU     18              ;jiffies before an arrow repeats
ARPT2   EQU     8               ;jiffies between repeats
;
ARCMDS  FDB     ARUP,ARDN,ARLF,ARRT
ARUP    FCC     'MOVE'
        FCB     C.CR,0
ARDN    FCC     'MOVE BACK'
        FCB     C.CR,0
ARLF    FCC     'TURN LEFT'
        FCB     C.CR,0
ARRT    FCC     'TURN RIGHT'
        FCB     C.CR,0
;
;  KEYMAP: keyboard matrix (row*8 + column) to ASCII.  The arrows
;  are handled above; 0 means ignore, $80 switches views.
;
KEYMAP  FCB     0,'A','B','C','D','E','F','G'
        FCB     'H','I','J','K','L','M','N','O'
        FCB     'P','Q','R','S','T','U','V','W'
        FCB     'X','Y','Z',0,0,0,0,C.SP
        FCC     '01234567'
        FCC     '89:;,-./'
        FCB     C.CR,$80,0,0,0,$80,0,0      ;ENTER CLEAR BRK ALT CTL F1 F2 SHF
;
;  TDNEAR: a creature moved; redraw if it is in (or next to) the
;          top-down window.  Called from CWALK with
;       A - |row difference|
;       B - |column difference|
;
TDNEAR  TST     TOPDN           ;top-down?
        BEQ     TDN90           ;   nope
        CMPA    #TDROWS/2+1     ;   .
        BHI     TDN90           ;   .
        CMPB    #TDCOLS/2+1     ;   .
        BHI     TDN90           ;   .
        DEC     NEWLUK          ;request a (delayed) update
TDN90   RTS
;
;!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
;  T O P - D O W N   V I E W
;!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
;
;  TDVIEW: replaces VIEWER while TOPDN is set
;
TDVIEW  SWI                     ;blank the 1-bit view (U <- FLOP VDB)
        FCB     ZFLOP           ;   .
        LBSR    TAGPTR          ;this buffer's frame is top-down
        LDA     #1              ;   .
        STA     ,X              ;   .
;
;  TDREND: draw the view into the hidden GIME screen
;
TDREND  PSHS    A,B,X,Y,U       ;save regs
        LDA     LEVEL           ;new level?
        INCA                    ;   .
        CMPA    SEENLV          ;   .
        BEQ     TDR05           ;   nope
        STA     SEENLV          ;forget what we have seen
        LDX     #SEEN           ;   .
TDR02   CLR     ,X+             ;   .
        CMPX    #SEEN+128       ;   .
        BLO     TDR02           ;   .
TDR05   LBSR    TDLOS           ;what can we see, and how well?
        LBSR    TDOCC           ;who and what is where?
        LDA     FRONT           ;draw on the hidden screen
        EORA    #1              ;   .
        LBSR    MAPPF           ;   .
        LDX     #SCRTD          ;   .
        LDB     #1              ;   .
        STB     A,X             ;   .
;
        CLR     TDIDX           ;walk the window
        CLR     TDWR            ;   .
TDR10   LDB     TDWR            ;rows clipped at the top/bottom
        CLRA                    ;   .
        CMPB    #0              ;   .
        BNE     TDR12           ;   .
        LDA     #8              ;   .
TDR12   STA     CLTOP           ;   .
        LDA     #24             ;   .
        CMPB    #TDROWS-1       ;   .
        BNE     TDR14           ;   .
        LDA     #16             ;   .
TDR14   STA     CLBOT           ;   .
        LDX     #ROWBAS         ;   .
        LSLB                    ;   .
        LDD     B,X             ;   .
        STD     TDTMP           ;   .
        CLR     TDWC            ;   .
TDR20   LDA     TDWC            ;screen addr of the cell
        LDB     #12             ;   .
        MUL                     ;   .
        ADDD    TDTMP           ;   .
        STD     TDBASE          ;   .
        LDA     TDWR            ;maze position of the cell
        ADDA    PROW            ;   .
        SUBA    #TDROWS/2       ;   .
        STA     TDROW           ;   .
        LDA     TDWC            ;   .
        ADDA    PCOL            ;   .
        SUBA    #TDCOLS/2       ;   .
        STA     TDCOL           ;   .
        LDD     TDTMP           ;   .
        PSHS    A,B             ;   (DRCELL uses TDTMP)
        LBSR    DRCELL          ;   .
        PULS    A,B             ;   .
        STD     TDTMP           ;   .
        INC     TDIDX           ;   .
        INC     TDWC            ;   .
        LDA     TDWC            ;   .
        CMPA    #TDCOLS         ;   .
        BLO     TDR20           ;   .
        INC     TDWR            ;   .
        LDA     TDWR            ;   .
        CMPA    #TDROWS         ;   .
        BLO     TDR10           ;   .
;
        LBSR    DRHERO          ;and us, in the middle
        PULS    A,B,X,Y,U,PC    ;restore regs/exit
;
;  ROWBAS: screen addr of row 0 of each window row (+2 byte margin)
;
ROWBAS  FDB     SCRWIN+((24*0-8)*SCRBPR)+2
        FDB     SCRWIN+((24*1-8)*SCRBPR)+2
        FDB     SCRWIN+((24*2-8)*SCRBPR)+2
        FDB     SCRWIN+((24*3-8)*SCRBPR)+2
        FDB     SCRWIN+((24*4-8)*SCRBPR)+2
        FDB     SCRWIN+((24*5-8)*SCRBPR)+2
        FDB     SCRWIN+((24*6-8)*SCRBPR)+2
;
TILOFF  FDB     0*TILESZ,1*TILESZ,2*TILESZ,3*TILESZ
        FDB     4*TILESZ,5*TILESZ,6*TILESZ,7*TILESZ
        FDB     8*TILESZ,9*TILESZ,10*TILESZ,11*TILESZ
        FDB     12*TILESZ,13*TILESZ,14*TILESZ,15*TILESZ
;
SIDMSK  FCB     %00000011,%00001100,%00110000,%11000000
BITTAB  FCB     $01,$02,$04,$08,$10,$20,$40,$80
;
;  TDLOS: line of sight, distance and light for every window cell
;
;  For each cell the table holds two paths from the player (they
;  differ only where the line passes exactly through a corner); the
;  cell is in sight if either path crosses only open passages.
;  Light follows SETFAD: v = light - 7 - distance.
;
TDLOS   LDA     #TDSPRB         ;the table lives in the sprite block
        STA     MMUSL5          ;   .
        LDY     #LOSTAB         ;   .
        CLR     TDWR            ;   .
        CLR     TDWC            ;   .
        CLRB                    ;cell index
TDL10   PSHS    B               ;   .
        LDA     ,Y              ;distance
        LDX     #TDDST          ;   .
        STA     B,X             ;   .
        LEAU    2,Y             ;path A
        LDB     1,Y             ;   .
        LBSR    WALKP           ;   .
        BCS     TDL20           ;   clear
        LEAU    11,Y            ;path B
        LDB     1,Y             ;   .
        LBSR    WALKP           ;   .
TDL20   LDA     #0              ;   .
        BCC     TDL40           ;   out of sight
        LDA     RLIGHT          ;v = light - 7 - distance
        SUBA    #7              ;   .
        SUBA    ,Y              ;   .
        LBSR    SHADEV          ;   .
        TSTA                    ;lit?
        BEQ     TDL30           ;   nope
        PSHS    A               ;we have seen this cell
        LDA     TDWR            ;   .
        ADDA    PROW            ;   .
        SUBA    #TDROWS/2       ;   .
        LDB     TDWC            ;   .
        ADDB    PCOL            ;   .
        SUBB    #TDCOLS/2       ;   .
        LBSR    SEENAD          ;   .
        ORA     ,X              ;   .
        STA     ,X              ;   .
        PULS    A               ;   .
TDL30   ORA     #$80            ;in sight
TDL40   LDB     ,S              ;   .
        LDX     #TDLIT          ;   .
        STA     B,X             ;   .
        LEAY    LOSREC,Y        ;next cell
        INC     TDWC            ;   .
        LDA     TDWC            ;   .
        CMPA    #TDCOLS         ;   .
        BLO     TDL50           ;   .
        CLR     TDWC            ;   .
        INC     TDWR            ;   .
TDL50   PULS    B               ;   .
        INCB                    ;   .
        CMPB    #TDCELS         ;   .
        BLO     TDL10           ;   .
        RTS
;
;  WALKP: walk a path of directions from the player
;
;  Inputs:
;       U - path, B - steps
;  Returns:
;       C - set if every step crosses an open passage
;
WALKP   PSHS    B               ;steps left
        LDD     PROW            ;start where we stand
        STD     TDLR            ;   .
        TST     ,S              ;   .
        BEQ     WKOK            ;   .
WK10    LDD     TDLR            ;   .
        JSR     MAP32           ;   .
        LDA     ,X              ;   .
        CMPA    #$FF            ;   .
        BEQ     WKNO            ;   .
        LDB     ,U+             ;direction
        LDX     #SIDMSK         ;passage that way?
        ANDA    B,X             ;   .
        BNE     WKNO            ;   nope
        LDX     #STPTAB         ;take the step
        LSLB                    ;   .
        LDD     B,X             ;   .
        ADDA    TDLR            ;   .
        CMPA    #31             ;   .
        BHI     WKNO            ;   .
        STA     TDLR            ;   .
        ADDB    TDLC            ;   .
        CMPB    #31             ;   .
        BHI     WKNO            ;   .
        STB     TDLC            ;   .
        DEC     ,S              ;   .
        BNE     WK10            ;   .
        LDD     TDLR            ;   .
        JSR     MAP32           ;   .
        LDA     ,X              ;   .
        CMPA    #$FF            ;   .
        BEQ     WKNO            ;   .
WKOK    PULS    B               ;   .
        ORCC    #CC.C           ;   .
        RTS
WKNO    PULS    B               ;   .
        ANDCC   #~CC.C&$FF      ;   .
        RTS
;
;  SHADEV: A <- light level 0-4 for v = A (signed); 4 = full light
;
SHADEV  TSTA                    ;   .
        BGE     SHV4            ;   .
        CMPA    #-2             ;   .
        BGE     SHV3            ;   .
        CMPA    #-4             ;   .
        BGE     SHV2            ;   .
        CMPA    #-6             ;   .
        BGE     SHV1            ;   .
        CLRA                    ;   .
        RTS
SHV4    LDA     #4              ;   .
        RTS
SHV3    LDA     #3              ;   .
        RTS
SHV2    LDA     #2              ;   .
        RTS
SHV1    LDA     #1              ;   .
        RTS
;
;  SEENAD: X <- SEEN byte, A <- bit for row A, column B
;
SEENAD  PSHS    B               ;   .
        LDX     #SEEN           ;   .
        LSLA                    ;row * 4
        LSLA                    ;   .
        LEAX    A,X             ;   .
        LSRB                    ;column / 8
        LSRB                    ;   .
        LSRB                    ;   .
        ABX                     ;   .
        PULS    B               ;   .
        ANDB    #7              ;   .
        PSHS    X               ;   .
        LDX     #BITTAB         ;   .
        LDA     B,X             ;   .
        PULS    X,PC            ;   .
;
;  TDOCC: note the creatures and floor objects in the window
;
TDOCC   LDX     #TDCRE          ;forget the last frame's
TDO02   CLR     ,X+             ;   .
        CMPX    #TDITM+TDCELS   ;   .
        BLO     TDO02           ;   .
        LDY     #CCBLND         ;creatures
TDO10   TST     P.CCUSE,Y       ;alive?
        BEQ     TDO20           ;   .
        LDD     P.CCROW,Y       ;in the window?
        LBSR    WINIDX          ;   .
        BCC     TDO20           ;   .
        LDA     P.CCTYP,Y       ;type+1, bit 7 if magical
        INCA                    ;   .
        TST     P.CCMGO,Y       ;   .
        BEQ     TDO12           ;   .
        ORA     #$80            ;   .
TDO12   LDX     #TDCRE          ;   .
        STA     B,X             ;   .
TDO20   LEAY    CC.LEN,Y        ;   .
        CMPY    #CCBEND         ;   .
        BNE     TDO10           ;   .
;
        LDY     #OCBLND         ;objects lying on this level's floor
TDO30   CMPY    OCBPTR          ;   .
        BHS     TDO90           ;   .
        LDA     P.OCLVL,Y       ;   .
        CMPA    LEVEL           ;   .
        BNE     TDO40           ;   .
        TST     P.OCOWN,Y       ;   .
        BNE     TDO40           ;   .
        LDD     P.OCROW,Y       ;   .
        LBSR    WINIDX          ;   .
        BCC     TDO40           ;   .
        LDA     P.OCCLS,Y       ;class+1
        INCA                    ;   .
        LDX     #TDITM          ;   .
        STA     B,X             ;   .
TDO40   LEAY    OC.LEN,Y        ;   .
        BRA     TDO30           ;   .
TDO90   RTS
;
;  WINIDX: window cell index of row A, column B
;
;  Returns:
;       B - index
;       C - set if the cell is in the window
;
WINIDX  SUBA    PROW            ;   .
        ADDA    #TDROWS/2       ;   .
        CMPA    #TDROWS-1       ;   .
        BHI     WIX90           ;   .
        SUBB    PCOL            ;   .
        ADDB    #TDCOLS/2       ;   .
        CMPB    #TDCOLS-1       ;   .
        BHI     WIX90           ;   .
        PSHS    B               ;   .
        LDB     #TDCOLS         ;   .
        MUL                     ;   .
        ADDB    ,S+             ;   .
        ORCC    #CC.C           ;   .
        RTS
WIX90   ANDCC   #~CC.C&$FF      ;   .
        RTS
;
;  DRCELL: draw one window cell
;
DRCELL  LDA     TDROW           ;off the edge of the maze?
        CMPA    #31             ;   .
        LBHI    DRBLK           ;   .
        LDB     TDCOL           ;   .
        CMPB    #31             ;   .
        LBHI    DRBLK           ;   .
        JSR     MAP32           ;   .
        LDA     ,X              ;   .
        STA     TDCELL          ;   .
        CMPA    #$FF            ;solid rock?
        LBEQ    DRROCK          ;   .
;
;  Floor: pick the light level's tile set
;
        LDX     #TDLIT          ;   .
        LDB     TDIDX           ;   .
        LDA     B,X             ;   .
        STA     TDVIS           ;   .
        ANDA    #7              ;lit?
        BEQ     DRF02           ;   nope
        NEGA                    ;set = TDTILE + 4 - light
        ADDA    #TDTILE+4       ;   .
        BRA     DRF04           ;   .
DRF02   LDA     TDROW           ;seen before?
        LDB     TDCOL           ;   .
        LBSR    SEENAD          ;   .
        ANDA    ,X              ;   .
        LBEQ    DRBLK           ;   nope - darkness
        LDA     #TDTILE+4       ;remembered
DRF04   STA     TDSET           ;   .
        STA     MMUSL5          ;   .
;
        LDD     TDROW           ;hole or ladder here?
        JSR     VFIND           ;   .
        BMI     DRF06           ;   nope
        LDX     #T.VERT         ;   .
        BRA     DRF08           ;   .
DRF06   LDA     TDROW           ;floor variant (row*7 + col*3) & 3
        LDB     #7              ;   .
        MUL                     ;   .
        PSHS    B               ;   .
        LDA     TDCOL           ;   .
        LDB     #3              ;   .
        MUL                     ;   .
        ADDB    ,S+             ;   .
        TFR     B,A             ;   .
        ANDA    #3              ;   .
        LDX     #T.FLOR         ;   .
DRF08   LSLA                    ;   .
        LDY     #TILOFF         ;   .
        LDD     A,Y             ;   .
        LEAX    D,X             ;   .
        LBSR    BLTILE          ;   .
;
;  Walls and doors on the cell's edges
;
        CLRB                    ;direction
DRF10   PSHS    B               ;   .
        LDA     TDCELL          ;side = (cell >> 2d) & 3
        TSTB                    ;   .
        BEQ     DRF14           ;   .
DRF12   LSRA                    ;   .
        LSRA                    ;   .
        DECB                    ;   .
        BNE     DRF12           ;   .
DRF14   ANDA    #3              ;   .
        BEQ     DRF30           ;   open
        STA     TDTMP           ;   .
        LDB     ,S              ;neighbour solid rock? (it draws its own face)
        LDX     #STPTAB         ;   .
        LSLB                    ;   .
        LDD     B,X             ;   .
        ADDA    TDROW           ;   .
        ADDB    TDCOL           ;   .
        LBSR    RKOPEN          ;   .
        BEQ     DRF30           ;   .
        CLRA                    ;kind 0: wall
        LDB     TDTMP           ;   .
        CMPB    #HF.WAL         ;   .
        BEQ     DRF20           ;   .
        INCA                    ;kind 1: door
        CMPB    #HF.DOR         ;   .
        BEQ     DRF20           ;   .
        LBSR    MAGLV           ;secret door: magic light shows it
        TSTA                    ;   .
        BEQ     DRF20           ;   (A = 0: drawn as a wall)
        LDA     TDVIS           ;   and only in a lit cell
        ANDA    #7              ;   .
        BEQ     DRF20           ;   .
        LDA     #2              ;kind 2: secret door
DRF20   PSHS    A               ;kind
        LDB     1,S             ;strip table entry for this side
        LDA     #7              ;   .
        MUL                     ;   .
        LDX     #STRTAB         ;   .
        ABX                     ;   .
        PULS    A               ;   .
        LDB     2,X             ;bytes per strip
        MUL                     ;   * kind
        ADDD    ,X              ;   + base
        TFR     D,U             ;   .
        LDY     3,X             ;y0, h
        LDA     5,X             ;width
        STA     TDW             ;   .
        LDA     6,X             ;x offset
        STA     TDXOF           ;   .
        TFR     U,X             ;   .
        TFR     Y,D             ;   .
        LBSR    BLTOP           ;   .
DRF30   PULS    B               ;   .
        INCB                    ;   .
        CMPB    #4              ;   .
        BLO     DRF10           ;   .
;
;  Objects and creatures
;
        LDX     #TDITM          ;object here?
        LDB     TDIDX           ;   .
        LDA     B,X             ;   .
        BEQ     DRF50           ;   .
        DECA                    ;   .
        PSHS    A               ;   .
        LBSR    MAGLV           ;seen by regular or magic light
        LDB     TDVIS           ;   .
        ANDB    #7              ;   .
        PSHS    B               ;   .
        CMPA    ,S+             ;   .
        BHS     DRF40           ;   .
        TFR     B,A             ;   .
DRF40   PULS    B               ;class
        LBSR    SPRSET          ;sprite block for light A
        BEQ     DRF50           ;   not seen
        LDA     #120            ;   .
        MUL                     ;   .
        ADDD    #S.ITEM         ;   .
        TFR     D,X             ;   .
        CLR     TDXOF           ;   .
        LDA     #6              ;   .
        STA     TDW             ;   .
        LDD     #$0D0A          ;rows 13-22
        LBSR    BLTMS           ;   .
;
DRF50   LDX     #TDCRE          ;creature here?
        LDB     TDIDX           ;   .
        LDA     B,X             ;   .
        BEQ     DRF90           ;   .
        PSHS    A               ;   .
        BMI     DRF52           ;magical: needs magic light
        LDA     TDVIS           ;   .
        ANDA    #7              ;   .
        BRA     DRF54           ;   .
DRF52   LBSR    MAGLV           ;   .
DRF54   LBSR    SPRSET          ;   .
        PULS    A               ;   .
        BEQ     DRF90           ;   not seen
        ANDA    #$7F            ;type
        DECA                    ;   .
        CLRB                    ;   * 256
        ADDD    #S.CRE          ;   .
        TFR     D,X             ;   .
        LDA     #2              ;centred, or to the right of us
        LDB     TDIDX           ;   .
        CMPB    #TDCELS/2       ;   .
        BNE     DRF56           ;   .
        LDA     #4              ;   .
DRF56   STA     TDXOF           ;   .
        LDA     #8              ;   .
        STA     TDW             ;   .
        LDD     #$0410          ;rows 4-19
        LBSR    BLTMS           ;   .
DRF90   RTS
;
;  STRTAB: per side - strip base, bytes per strip, y0, rows, width, x
;
STRTAB  FDB     T.STRN
        FCB     NS.H*12,0,NS.H,12,0
        FDB     T.STRE
        FCB     24*2,0,24,2,10
        FDB     T.STRS
        FCB     SS.H*12,24-SS.H,SS.H,12,0
        FDB     T.STRW
        FCB     24*2,0,24,2,0
;
;  MAGLV: A <- magic light level (0-4) of this cell, 0 if out of sight
;
MAGLV   PSHS    B,X             ;save regs
        CLRA                    ;   .
        TST     TDVIS           ;in sight?
        BPL     MGL90           ;   nope
        LDX     #TDDST          ;v = magic light - 7 - distance
        LDB     TDIDX           ;   .
        LDB     B,X             ;   .
        PSHS    B               ;   .
        LDA     MLIGHT          ;   .
        SUBA    #7              ;   .
        SUBA    ,S+             ;   .
        LBSR    SHADEV          ;   .
MGL90   PULS    B,X,PC          ;restore regs/exit
;
;  SPRSET: map in the sprites for light level A (0-4)
;  Returns:
;       Z - set if A = 0 (not seen)
;
SPRSET  PSHS    A               ;save regs
        TSTA                    ;   .
        BEQ     SPS90           ;   .
        CMPA    #3              ;dim below level 3
        LDA     #TDSPRB         ;   .
        BHS     SPS10           ;   .
        INCA                    ;   .
SPS10   STA     MMUSL5          ;   .
        ANDCC   #~CC.Z&$FF      ;   .
SPS90   PULS    A,PC            ;   (PULS leaves CC alone)
;
;  DRROCK: solid rock - lit from its brightest open neighbour,
;          shaped by which neighbours are open
;
DRROCK  CLR     TDMSK           ;   .
        CLR     TDSHD           ;   .
        CLR     TDTMP+1         ;any open neighbour seen before?
        LDA     TDROW           ;north
        DECA                    ;   .
        LDB     TDCOL           ;   .
        LBSR    RKOPEN          ;   .
        BEQ     DRK10           ;   .
        LDA     #1              ;   .
        LBSR    RKMSK           ;   .
        TST     TDWR            ;   .
        BEQ     DRK10           ;   .
        LDB     TDIDX           ;   .
        SUBB    #TDCOLS         ;   .
        LBSR    RKLIT           ;   .
DRK10   LDA     TDROW           ;east
        LDB     TDCOL           ;   .
        INCB                    ;   .
        LBSR    RKOPEN          ;   .
        BEQ     DRK20           ;   .
        LDA     #2              ;   .
        LBSR    RKMSK           ;   .
        LDA     TDWC            ;   .
        CMPA    #TDCOLS-1       ;   .
        BEQ     DRK20           ;   .
        LDB     TDIDX           ;   .
        INCB                    ;   .
        LBSR    RKLIT           ;   .
DRK20   LDA     TDROW           ;south
        INCA                    ;   .
        LDB     TDCOL           ;   .
        LBSR    RKOPEN          ;   .
        BEQ     DRK30           ;   .
        LDA     #4              ;   .
        LBSR    RKMSK           ;   .
        LDA     TDWR            ;   .
        CMPA    #TDROWS-1       ;   .
        BEQ     DRK30           ;   .
        LDB     TDIDX           ;   .
        ADDB    #TDCOLS         ;   .
        LBSR    RKLIT           ;   .
DRK30   LDA     TDROW           ;west
        LDB     TDCOL           ;   .
        DECB                    ;   .
        LBSR    RKOPEN          ;   .
        BEQ     DRK40           ;   .
        LDA     #8              ;   .
        LBSR    RKMSK           ;   .
        TST     TDWC            ;   .
        BEQ     DRK40           ;   .
        LDB     TDIDX           ;   .
        DECB                    ;   .
        LBSR    RKLIT           ;   .
;
DRK40   LDA     TDSHD           ;lit?
        BEQ     DRK42           ;   nope
        NEGA                    ;   .
        ADDA    #TDTILE+4       ;   .
        BRA     DRK44           ;   .
DRK42   TST     TDTMP+1         ;next to somewhere we've been?
        BEQ     DRBLK           ;   nope - darkness
        LDA     #TDTILE+4       ;   .
DRK44   STA     MMUSL5          ;   .
        LDA     TDMSK           ;   .
        LSLA                    ;   .
        LDY     #TILOFF         ;   .
        LDD     A,Y             ;   .
        ADDD    #T.ROCK         ;   .
        TFR     D,X             ;   .
        BRA     BLTILE          ;   .
;
RKMSK   ORA     TDMSK           ;   .
        STA     TDMSK           ;   .
        RTS
;
RKLIT   LDX     #TDLIT          ;neighbour's light
        LDA     B,X             ;   .
        ANDA    #7              ;   .
        CMPA    TDSHD           ;   .
        BLS     RKL90           ;   .
        STA     TDSHD           ;   .
RKL90   RTS
;
;  RKOPEN: is row A, column B open floor?  (notes in TDTMP+1 if it
;          has been seen)
;  Returns:
;       Z - clear if open
;
RKOPEN  CMPA    #31             ;   .
        BHI     RKO80           ;   .
        CMPB    #31             ;   .
        BHI     RKO80           ;   .
        PSHS    A,B             ;   .
        JSR     MAP32           ;   .
        LDA     ,X              ;   .
        CMPA    #$FF            ;   .
        PULS    A,B             ;   .
        BEQ     RKO90           ;   rock
        LBSR    SEENAD          ;   .
        ANDA    ,X              ;   .
        BEQ     RKO70           ;   .
        STA     TDTMP+1         ;   .
RKO70   ANDCC   #~CC.Z&$FF      ;open
        RTS
RKO80   ORCC    #CC.Z           ;   .
RKO90   RTS
;
;  DRBLK: nothing to see - black
;
DRBLK   LDX     #0              ;   .
        CLR     TDTMP           ;   (no source)
        CLR     TDXOF           ;   .
        LDD     #$0018          ;rows 0-23
        LBSR    CLIP            ;   .
        BEQ     DRB90           ;   .
        LDD     #0              ;   .
DRB10   STD     ,U              ;   .
        STD     2,U             ;   .
        STD     4,U             ;   .
        STD     6,U             ;   .
        STD     8,U             ;   .
        STD     10,U            ;   .
        LEAU    SCRBPR,U        ;   .
        DEC     TDCNT           ;   .
        BNE     DRB10           ;   .
DRB90   RTS
;
;  BLTILE: copy a whole tile (X) into the cell
;
BLTILE  LDA     #12             ;   .
        STA     TDW             ;   .
        CLR     TDXOF           ;   .
        LDD     #$0018          ;rows 0-23
;
;  BLTOP: copy an opaque picture into the cell
;
;  Inputs:
;       X - source, TDW bytes per row
;       A - first row (in the cell), B - rows
;       TDW, TDXOF - width and offset in bytes
;
BLTOP   PSHS    A               ;   .
        LDA     TDW             ;source stride
        STA     TDTMP           ;   .
        PULS    A               ;   .
        LBSR    CLIP            ;   .
        BEQ     BLT90           ;   .
        LDA     TDW             ;   .
        CMPA    #12             ;   .
        BEQ     BLT20           ;   .
BLT10   LDB     TDW             ;   .
        PSHS    U               ;   .
BLT12   LDA     ,X+             ;   .
        STA     ,U+             ;   .
        DECB                    ;   .
        BNE     BLT12           ;   .
        PULS    U               ;   .
        LEAU    SCRBPR,U        ;   .
        DEC     TDCNT           ;   .
        BNE     BLT10           ;   .
BLT90   RTS
;
BLT20   LDD     ,X              ;12 bytes a row, unrolled
        STD     ,U              ;   .
        LDD     2,X             ;   .
        STD     2,U             ;   .
        LDD     4,X             ;   .
        STD     4,U             ;   .
        LDD     6,X             ;   .
        STD     6,U             ;   .
        LDD     8,X             ;   .
        STD     8,U             ;   .
        LDD     10,X            ;   .
        STD     10,U            ;   .
        LEAX    12,X            ;   .
        LEAU    SCRBPR,U        ;   .
        DEC     TDCNT           ;   .
        BNE     BLT20           ;   .
        RTS
;
;  BLTMS: draw a masked sprite into the cell (rows of mask,data
;         byte pairs); inputs as BLTOP
;
BLTMS   PSHS    A               ;   .
        LDA     TDW             ;source stride = 2 * width
        LSLA                    ;   .
        STA     TDTMP           ;   .
        PULS    A               ;   .
        LBSR    CLIP            ;   .
        BEQ     BLM90           ;   .
BLM10   LDB     TDW             ;   .
        PSHS    U               ;   .
BLM12   LDA     ,U              ;   .
        ANDA    ,X+             ;   .
        ORA     ,X+             ;   .
        STA     ,U+             ;   .
        DECB                    ;   .
        BNE     BLM12           ;   .
        PULS    U               ;   .
        LEAU    SCRBPR,U        ;   .
        DEC     TDCNT           ;   .
        BNE     BLM10           ;   .
BLM90   RTS
;
;  CLIP: clip rows A..A+B-1 of a picture to the window row
;
;  Inputs:
;       X - source row 0, TDTMP - source bytes per row
;  Returns:
;       X - first visible source row
;       U - its screen addr (TDBASE + row*160 + TDXOF)
;       TDCNT - rows; Z set if none
;
CLIP    PSHS    A               ;y0
        ADDB    ,S              ;end
        CMPB    CLBOT           ;   .
        BLS     CLP10           ;   .
        LDB     CLBOT           ;   .
CLP10   CMPA    CLTOP           ;   .
        BHS     CLP20           ;   .
        LDA     CLTOP           ;   .
CLP20   PSHS    A               ;top
        SUBB    ,S              ;rows = end - top
        BLS     CLP90           ;   none
        STB     TDCNT           ;   .
        SUBA    1,S             ;source += (top - y0) * stride
        LDB     TDTMP           ;   .
        MUL                     ;   .
        LEAX    D,X             ;   .
        LDA     ,S              ;dest = TDBASE + top*160 + TDXOF
        LDB     #SCRBPR         ;   .
        MUL                     ;   .
        ADDD    TDBASE          ;   .
        ADDB    TDXOF           ;   .
        ADCA    #0              ;   .
        TFR     D,U             ;   .
        LEAS    2,S             ;   .
        TST     TDCNT           ;Z clear
        RTS
CLP90   LEAS    2,S             ;   .
        CLR     TDCNT           ;Z set
        RTS
;
;  DRHERO: the player, and an arrow on the side we face
;
DRHERO  LDX     #ROWBAS+(TDROWS/2)*2
        LDD     ,X              ;   .
        ADDD    #(TDCOLS/2)*12  ;   .
        STD     TDBASE          ;   .
        CLR     CLTOP           ;   .
        LDA     #24             ;   .
        STA     CLBOT           ;   .
        LDA     #TDSPRB         ;   .
        STA     MMUSL5          ;   .
        LDA     #2              ;centred, or left of a creature
        LDX     #TDCRE          ;   .
        TST     TDCELS/2,X      ;   .
        BEQ     DRH10           ;   .
        CLRA                    ;   .
DRH10   STA     TDXOF           ;   .
        LDA     #8              ;   .
        STA     TDW             ;   .
        LDX     #S.HERO         ;   .
        LDD     #$0410          ;rows 4-19
        LBSR    BLTMS           ;   .
        LDB     PDIR            ;the arrow
        ANDB    #3              ;   .
        LDX     #ARRTAB         ;   .
        LSLB                    ;   *6
        LEAX    B,X             ;   .
        LSLB                    ;   .
        LEAX    B,X             ;   .
        LDA     4,X             ;   .
        STA     TDW             ;   .
        LDA     5,X             ;   .
        STA     TDXOF           ;   .
        LDD     2,X             ;y0, rows
        LDX     ,X              ;   .
        LBRA    BLTMS           ;   .
;
ARRTAB  FDB     S.ARRN
        FCB     0,4,4,4         ;north: y0, rows, width, x
        FDB     S.ARRE
        FCB     8,8,2,10        ;east
        FDB     S.ARRS
        FCB     20,4,4,4        ;south
        FDB     S.ARRW
        FCB     8,8,2,0         ;west
;
        IFGT    *-CODEND
        ERROR   "CoCo 3 engine overlaps its tables"
        ENDC
