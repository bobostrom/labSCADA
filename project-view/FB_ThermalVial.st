(* ==============================================================================
   FUNCTION BLOCK: FB_ThermalVial
   DESCRIPTION: First-order thermal mass low-pass filter (EWMA) emulating a
                temperature sensor immersed in a glycol, mineral-oil, or sand vial.
                - Scan-rate independent discrete update driven by tSampleTick
                - Instant seed on cold boot or recovery from probe/comms fault
                - Immediate -999.0 pass-through during invalid/faulted readings
                - Set tThermalTau := T#0S for zero-lag raw pass-through
   ============================================================================== *)
FUNCTION_BLOCK FB_ThermalVial
VAR_INPUT
    rRawTemp            : REAL := -999.0;   (* Instantaneous valid air temperature (°C) *)
    bValid              : BOOL := FALSE;    (* TRUE when probe & comms are healthy *)
    tThermalTau         : TIME := T#5M;     (* First-order thermal time constant tau; T#0S bypasses filter *)
    tSampleTick         : TIME := T#5S;     (* Fixed EWMA update interval dt *)
END_VAR
VAR_OUTPUT
    rVialTemp           : REAL := -999.0;   (* Buffered virtual-vial temperature (°C), or -999.0 if invalid *)
END_VAR
VAR
    tonTick             : TON;
    rFilteredTemp       : REAL := -999.0;
    bPrimed             : BOOL := FALSE;
    tEffTick            : TIME;
    diDtMs              : DINT;
    diTauMs             : DINT;
    rAlpha              : REAL;
END_VAR
VAR CONSTANT
    cTempInvalid        : REAL := -999.0;
    cTimeZero           : TIME := T#0S;
    cDefaultSampleTick  : TIME := T#5S;
END_VAR
// --- implementation ---
IF NOT bValid THEN
    bPrimed       := FALSE;
    rFilteredTemp := cTempInvalid;
    tonTick(IN := FALSE, PT := tSampleTick);
ELSIF (tThermalTau <= cTimeZero) OR (NOT bPrimed) THEN
    bPrimed       := TRUE;
    rFilteredTemp := rRawTemp;
    tonTick(IN := FALSE, PT := tSampleTick);
ELSE
    IF tSampleTick > cTimeZero THEN
        tEffTick := tSampleTick;
    ELSE
        tEffTick := cDefaultSampleTick;
    END_IF;

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
