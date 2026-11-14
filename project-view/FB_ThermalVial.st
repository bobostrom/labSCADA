(* ==============================================================================
   FUNCTION BLOCK: FB_ThermalVial
   DESCRIPTION: First-order thermal mass low-pass filter (EWMA) emulating a
                temperature sensor immersed in a glycol, mineral-oil, or sand vial.
                - Scan-rate independent discrete update driven by tSampleTick
                - Instant seed on cold boot or recovery from probe/comms fault
                - Hold last buffered value across transient probe/comms dropouts up to tHoldoverGrace
                - Revert to -999.0 only after holdover expires (or immediately if never primed)
                - Set tThermalTau := T#0S for zero-lag raw pass-through
   ============================================================================== *)
FUNCTION_BLOCK FB_ThermalVial
VAR_INPUT
    rRawTemp            : REAL := -999.0;   (* Instantaneous valid air temperature (°C) *)
    bValid              : BOOL := FALSE;    (* TRUE when probe & comms are healthy *)
    tThermalTau         : TIME := T#5M;     (* First-order thermal time constant tau; T#0S bypasses filter *)
    tSampleTick         : TIME := T#5S;     (* Fixed EWMA update interval dt *)
    tHoldoverGrace      : TIME := T#5M;     (* Max holdover across brief dropouts; T#0S disables holdover *)
END_VAR
VAR_OUTPUT
    rVialTemp           : REAL := -999.0;   (* Buffered virtual-vial temperature (°C), or -999.0 if invalid *)
END_VAR
VAR
    tonTick             : TON;
    tonHoldover         : TON;
    rFilteredTemp       : REAL := -999.0;
    bPrimed             : BOOL := FALSE;
    bInputOk            : BOOL := FALSE;
    tEffTick            : TIME;
    diDtMs              : DINT;
    diTauMs             : DINT;
    rAlpha              : REAL;
END_VAR
VAR CONSTANT
    cTempInvalid        : REAL := -999.0;
    cTempMinValid       : REAL := -273.0;
    cTempMaxValid       : REAL := 900.0;
    cTimeZero           : TIME := T#0S;
    cDefaultSampleTick  : TIME := T#5S;
END_VAR
// --- implementation ---
bInputOk := bValid AND (rRawTemp > cTempMinValid) AND (rRawTemp < cTempMaxValid);
IF tSampleTick > cTimeZero THEN
    tEffTick := tSampleTick;
ELSE
    tEffTick := cDefaultSampleTick;
END_IF;

IF NOT bInputOk THEN
    tonTick(IN := FALSE, PT := tEffTick);
    IF bPrimed AND (tHoldoverGrace > cTimeZero) THEN
        tonHoldover(IN := TRUE, PT := tHoldoverGrace);
        IF tonHoldover.Q THEN
            tonHoldover(IN := FALSE, PT := tHoldoverGrace);
            bPrimed       := FALSE;
            rFilteredTemp := cTempInvalid;
        END_IF;
    ELSE
        tonHoldover(IN := FALSE, PT := tHoldoverGrace);
        bPrimed       := FALSE;
        rFilteredTemp := cTempInvalid;
    END_IF;
ELSIF (tThermalTau <= cTimeZero) OR (NOT bPrimed) THEN
    tonHoldover(IN := FALSE, PT := tHoldoverGrace);
    bPrimed       := TRUE;
    rFilteredTemp := rRawTemp;
    tonTick(IN := FALSE, PT := tEffTick);
ELSE
    tonHoldover(IN := FALSE, PT := tHoldoverGrace);
    tonTick(IN := TRUE, PT := tEffTick);
    IF tonTick.Q THEN
        tonTick(IN := FALSE, PT := tEffTick);
        diDtMs        := TIME_TO_DINT(tEffTick);
        diTauMs       := TIME_TO_DINT(tThermalTau);
        rAlpha        := TO_REAL(diDtMs) / TO_REAL(diTauMs + diDtMs);
        rFilteredTemp := rFilteredTemp + rAlpha * (rRawTemp - rFilteredTemp);
    END_IF;
END_IF;

rVialTemp := rFilteredTemp;
END_FUNCTION_BLOCK
