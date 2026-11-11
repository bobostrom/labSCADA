FUNCTION_BLOCK FB_RandomGenerator
VAR_INPUT
    bExecute: BOOL; (* Set TRUE to calculate next random number *)
    diMin: DINT; (* Inclusive minimum value *)
    diMax: DINT; (* Inclusive maximum value *)
END_VAR
VAR_OUTPUT
    diResult: DINT; (* Generated random number *)
END_VAR
VAR
    udiSeed: UDINT := 123456789; (* Initial non-zero seed *)
    udiRange: UDINT;
END_VAR
// --- implementation ---
IF bExecute THEN
    (* LCG Formula: X_{n+1} = (a * X_n + c) mod 2^32 *)
    udiSeed := (udiSeed * 1664525) + 1013904223;

    (* Scale the 32-bit value to the requested [diMin..diMax] range *)
    IF diMax >= diMin THEN
        udiRange := DINT_TO_UDINT(diMax - diMin + 1);
        diResult := diMin + UDINT_TO_DINT(udiSeed MOD udiRange);
    ELSE
        diResult := diMin;
    END_IF;
END_IF;
END_FUNCTION_BLOCK
