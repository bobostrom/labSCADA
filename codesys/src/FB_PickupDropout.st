(* ==============================================================================
   FUNCTION BLOCK: FB_PickupDropout
   DESCRIPTION: IEC 61131-3 Structured Text implementation of the SEL RTAC
                Pickup / Dropout timer (equivalent to RTAC PU_DO).

                - Pickup Delay (On-Delay / Timeout):
                  The input signal (IN) must remain continuously TRUE for
                  tPickupDelay before the output (Q) asserts to TRUE.
                  Nuisance spikes or transients shorter than tPickupDelay
                  are filtered out and reset the timer.

                - Dropout Delay (Off-Delay / Chatter Filter):
                  Once Q is TRUE (tripped), IN must remain continuously FALSE
                  for tDropoutDelay before Q resets to FALSE.
                  Any bounce or re-trip during the dropout window resets
                  the dropout timer, keeping Q asserted.
   ============================================================================== *)
FUNCTION_BLOCK FB_PickupDropout
VAR_INPUT
    {attribute 'symbol' := 'none'}
	IN              : BOOL;             (* Input signal to evaluate *)
    {attribute 'symbol' := 'none'}
    tPickupDelay    : TIME := T#0S;     (* Time IN must be sustained TRUE before Q asserts *)
    {attribute 'symbol' := 'none'}
    tDropoutDelay   : TIME := T#0S;     (* Time IN must be sustained FALSE before Q deasserts *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
	Q               : BOOL := FALSE;    (* Filtered output state *)
    {attribute 'symbol' := 'none'}
    bPickup         : BOOL := FALSE;    (* Raw instantaneous input status (unfiltered) *)
    {attribute 'symbol' := 'none'}
    tElapsedPU      : TIME := T#0S;     (* Elapsed pickup timer *)
    {attribute 'symbol' := 'none'}
    tElapsedDO      : TIME := T#0S;     (* Elapsed dropout timer *)
END_VAR
VAR
    {attribute 'symbol' := 'none'}
	tonPickup       : TON;
    {attribute 'symbol' := 'none'}
    tonDropout      : TON;
END_VAR

// Track raw instantaneous input
bPickup := IN;

IF NOT Q THEN
    // --- Alarm is currently OFF: Timing towards Pickup ---
    tonDropout(IN := FALSE, PT := tDropoutDelay);
    tElapsedDO := T#0S;

    tonPickup(IN := IN, PT := tPickupDelay);
    tElapsedPU := tonPickup.ET;

    IF tonPickup.Q THEN
        Q := TRUE;
    END_IF;
ELSE
    // --- Alarm is currently ON: Timing towards Dropout ---
    tonPickup(IN := FALSE, PT := tPickupDelay);
    tElapsedPU := tPickupDelay;

    tonDropout(IN := NOT IN, PT := tDropoutDelay);
    tElapsedDO := tonDropout.ET;

    IF tonDropout.Q THEN
        Q := FALSE;
    END_IF;
END_IF;





END_FUNCTION_BLOCK
