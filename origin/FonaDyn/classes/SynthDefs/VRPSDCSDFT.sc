// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

// This pseudo-UGen is a workaround for AverageOutput,
// which does not do what I want.
AverageOut {
	*ar { arg in, trig;
		var acc, avg, counter;

		counter = Phasor.ar(trig, 1, 1, 1000000, 1);
		acc = Phasor.ar(trig, in, 0, 100000, 0.0);
		avg = Delay1.ar(acc/counter);
		^Latch.ar(Delay1.ar(avg), trig);
	}
}

Accumulate {
	*ar { arg in, trig;
		var acc;

		acc = Phasor.ar(trig, in, 0, 100000, 0.0);
		^Latch.ar(Delay1.ar(acc), trig);
	}
}

CycleDuration {
	*ar { arg trig;
		var counter;

		counter = Phasor.ar(trig, 1, 1, 1000000, 1);
		^Latch.ar(Delay1.ar(counter), trig);
		}
}

VRPSDCSDFT {
//	classvar namePeakFollower = \sdPeakFollower;
	classvar namePhasePortrait = \sdPhasePortrait;
	classvar namePhasePortrait2 = \sdPhasePortrait2;
	classvar nameNDFTs = \sdNDFT;
	classvar nameDFTFilters = \sdDFTFilters;
	classvar nameQciDEGG = \sdQciDEGG;
	classvar nameHRFEGG = \sdHRFEGG;
//	classvar nameDiplo = \sdDiplo;
	const <eggNoiseMargin = 0.1;

	*compile { | libname, nHarmonics, tau, minFrequency, minSamples, clarityThresh |

		nHarmonics = nHarmonics.asInteger;
		minSamples = minSamples.asInteger;

/*		////////////////////////////////////////////////////////////////////////////////////////
		// Peak Follower SynthDef
		///////////////////////////////////////////////////////////////////////////////////////

		SynthDef(namePeakFollower,
			{ | aiBusConditionedEGG,
				aoBusGate, coBusEGGvalid |  			// Last arg added for compatibility only

				var in, inLP, dEGG, z;

				in = In.ar(aiBusConditionedEGG);		// Get the preconditioned EGG signal
				dEGG = in - Delay1.ar(in);				// Compute its "derivative"
				z = Dolansky.ar(dEGG, 0.99, 0.995);		// Trigger on dEGG cycles
				Out.ar(aoBusGate, [z]);
			}
		).add(libname); */

		////////////////////////////////////////////////////////////////////////////////////
		// Phase Portrait SynthDef
		////////////////////////////////////////////////////////////////////////////////////

		SynthDef(namePhasePortrait,
			{ | aiBusConditionedEGG,
				aoBusGate, coBusEGGvalid |  // Last arg added for compatibility only

				var in, inLP, integr, phi, z;

				integr = DC.ar(0.0); // Dummy to initialize the variable
				in = In.ar(aiBusConditionedEGG);     // Get the preconditioned EGG signal
				integr = Integrator.ar(in, 0.999, 0.05);  // works only from SC 3.7.x
				inLP = HPF.ar(integr, 50);			// Attenuate integrated DC shifts

				phi = atan2(in, inLP);				// Compute the analytic phase
				z = Dolansky.ar(phi, tau, 0.99);	// Cycle trigger
				Out.ar(aoBusGate, [z]);
				Out.kr(coBusEGGvalid, [DC.kr(1)]);	// Always ok (no validation)
			}
		).add(libname);

		////////////////////////////////////////////////////////////////////////////////////
		// Phase Portrait #2 SynthDef - same, and adds EGG validity check
		////////////////////////////////////////////////////////////////////////////////////

		SynthDef(namePhasePortrait2,
			{ | aiBusConditionedEGG,
				aoBusGate, coBusEGGvalid |

				var in, inLP, integr, z, phi;
				var period, period_1, ratio, eggGate;

				integr = DC.ar(0.0); 				// Dummy to initialize the variable
				in = In.ar(aiBusConditionedEGG);	// Get the preconditioned EGG signal
				integr = Integrator.ar(in, 0.999, 0.05);
				inLP = HPF.ar(integr, 50);			// Attenuate integrated DC shifts

				phi = atan2(in, inLP);				// Compute the 'analytic phase'
				z = Dolansky.ar(phi, tau, 0.99);	// Cycle trigger
				Out.ar(aoBusGate, [z]);

				///// EGG Validity check ////////////////////////////////////////////////
				// Valid if two consecutive period lengths differ by less than ~5% (1/20)

				period = CycleDuration.ar(z);
				period_1 = Latch.ar(Delay1.ar(period), z);
				ratio = MulAdd(( A2K.kr(period_1) / A2K.kr(period) ).log.abs, 20);
				eggGate = Select.kr(ratio, [DC.kr(1), DC.kr(0)]);
				Out.kr(coBusEGGvalid, eggGate);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////
		// N DFTs SynthDef  - the last 'harmonic' represents the power of all remaining harmonics
		///////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameNDFTs,
			{ | aiBusConditionedEGG,
				aiBusGateCycle,
				aoBusGateDFT,
				aoBusGateDelayedCycle,
				aoBusAmplitudeFirst,
				aoBusPhaseFirst |

				var in, gcycle, gDFT, gSkipped, gCycleDelayed;
				var length, gLength, inPower, invLength, amps, phases;
				var res, complex, complexAbs;
				var harmPower;
				var distortion, firstPower, harmsPower;
				var inAcc;

				in = In.ar(aiBusConditionedEGG);
				gcycle = In.ar(aiBusGateCycle);

				// Perform the DFT calculations for each cycle marked by gate gcycle
				// Ignores DFT cycles that are too long/short. Using default with a minimum of 10 samples
				// and a minimum of 50 cycles/s (typically equates to at most 882 samples)
				#gDFT, gSkipped, length ...res = DFT2.ar(in, gcycle, (1..nHarmonics), minFrequency, minSamples);
				gLength = Gate.ar(length, gDFT);   // DFT2 outputs zeros most of the time
				invLength = gLength.reciprocal;
				gCycleDelayed = gDFT + gSkipped;

				complex = nHarmonics collect: { | i | Complex(res[2*i], res[2*i+1]) };
				complexAbs = complex.abs * invLength;

				phases = complex.phase;

				// Equates the phase of "H" to that of the fundamental
				phases = phases.add(MulAdd(phases[0], 2, 0));

				harmsPower = 2.0 * Gate.ar(complexAbs[1..].squared.sum.sqrt, gDFT);

				// Compute total power in the analyzed harmonics 2..N and report as voltage level
				complexAbs = complexAbs.add(harmsPower);  // append as last element
				amps = complexAbs.ampdb * 0.1;   // operate with Bel rather than dB

				// The delayed cycle gate is simply whenever we skip or output a DFT for each input cycle
				Out.ar(aoBusGateDelayedCycle, [gCycleDelayed]);
				Out.ar(aoBusGateDFT, [gDFT]); // Whenever we have DFT output in amps/phases
				Out.ar(aoBusAmplitudeFirst, Gate.ar(amps, gDFT));
				Out.ar(aoBusPhaseFirst, Gate.ar(phases, gDFT));
			}
		).add(libname);

		////////////////////////////////////////////////////////////////////////
		// DFT Filters
		////////////////////////////////////////////////////////////////////////

		SynthDef(nameDFTFilters,
			{ | aiBusGateDFT,
				aiBusGateCycle,
				aiBusGateDelayedCycle,
				ciBusClarity,
				ciBusEGGvalid,
				aoBusGateFilteredDFT |

				// Grab maxSamples constant
				var maxSamples = SampleRate.ir / minFrequency;

				// Grab gates
				var gdft = In.ar(aiBusGateDFT);
				var gc = In.ar(aiBusGateCycle);
				var gdc = In.ar(aiBusGateDelayedCycle);
				var gout; // Output gate

				// Grab EGG cycle markers and delay them
				// Note that we need to delay the values measured at the end of each EGG cycle
				// until also the DFT output is ready (or skipped).
				var clarity;
				var trackTime;

				// Note that VariadicDelay.ar converts the control rate inputs into audio rate outputs
				// Hold the time stamp at the end of the most recent EGG cycle
				// until the DFT computation of that cycle is done
				trackTime = Gate.ar(VariadicDelay.ar([ Timestamp.ar ], gc, gdc, maxSamples), gdc);

				// The EGGvalid bus holds either 0 or 1; the Clarity bus holds any value between 0 and 1
				clarity = K2AN.ar(In.kr(ciBusClarity) * In.kr(ciBusEGGvalid));

				// Use the "Clarity" metric as a gate > 0.99 (ceil rounds up to the nearest integer)
				// i.e. we get 0 if clarity < threshold and 1 otherwise
				// The trig pulse gout gets the amplitude=trackTime (always > 0)

				gout = Select.ar(gdft * (clarity - clarityThresh).ceil, [DC.ar(0.0), trackTime]);

				/* MAYBE: NOT YET IMPLEMENTED
				// At high fo, conditionally reduce the client's fetch load
				// and the cycle rate to Log.aiff files
				// by skipping EGG cycles. Since we are inside a SynthDef,
				// this "if" statement controls the compilation of the enclosed code.
				if (bSkipping, {
					var iHz, iDivider;
					iHz = In.kr(ciBusFrequency).midicps;
					iDivider = iHz.div(400).max(1);
					gout = PulseDivider.ar(gout, K2AN.ar(iDivider));
				});
				*/

				Out.ar(aoBusGateFilteredDFT, [gout]);
			}
		).add(libname);


/*		////////////////////////////////////////////////////////////////////////////
		//  MAYBE: Resynthesize the EGG waveform from the Fourier descriptors
		////////////////////////////////////////////////////////////////////////////

		SynthDef(nameResynthEGG,
			{ | aiBusGateFilteredDFT,
				aiBusAmplitudeFirst,
				aiBusPhaseFirst,
				ciBusFreq,
				aoBusResynthEGG |
				var sum, linAmps;

				var phases = In.ar(aiBusPhaseFirst, nHarmonics);
				var cycleGate = In.ar(aiBusGateFilteredDFT, 1);
				var freqs = In.kr(ciBusFreq, 1).midicps*(1..nHarmonics);
				var amps   = In.ar(aiBusAmplitudeFirst, nHarmonics);
				linAmps = (amps*10).dbamp;
				sum = DynKlang.ar(`[freqs, linAmps, phases]);
				Out.ar(aoBusResynthEGG,  sum);
			}
		).add(libname);
*/

		/////////////////////////////////////////////////////////////////////////
		// dEGGmax and Qci and Ic SynthDef
		// This algorithm relies on the input signal being free of DC,
		// so it must use ConditionedEGG
		/////////////////////////////////////////////////////////////////////////

		SynthDef(nameQciDEGG,
			{ | aiBusConditionedEGG,
				aiBusGateCycle,
				aiBusGateDelayedCycle,
				aoBusDEGGmax,
				aoBusQcontact,
				aoBusIcontact |
				var integral, q, qd, peak2peak;
				var ticks, delta, slopeMax, ampScale, dEGGmax, iContact;

				var sig = In.ar(aiBusConditionedEGG);

				// Grab gates
				var gc   = In.ar(aiBusGateCycle);
				var gcd  = In.ar(aiBusGateDelayedCycle);
				var max  = RunningMax.ar(sig, gc);		// per-cycle max
				var min  = RunningMin.ar(sig, gc);		// per-cycle min
				peak2peak = min - max;

				// dEGGmax computation
				ticks = Sweep.ar(gc, SampleRate.ir);
				ampScale = (peak2peak*(-0.5)*sin(2pi/ticks)).reciprocal;
				delta = RunningMax.ar(sig - Delay1.ar(sig), gc);
				dEGGmax = delta*ampScale;

				// Qci computation
				integral = peak2peak.reciprocal * min;

				// iContact computation (minimize to zero)
				iContact = dEGGmax.max(1.0).log10 * integral;

				// Get the values just BEFORE the trigger
				q = Latch.ar(Delay1.ar([dEGGmax, integral, iContact]), gc);

				// Delay all of them, to synch with the DFT calculations
				qd = Gate.ar(VariadicDelay.ar(q, gc, gcd, 882), gcd);

				// We don't know if the output buses are next to each other,
				// so output them one by one.
				Out.ar(aoBusDEGGmax,  qd[0]);
				Out.ar(aoBusQcontact, qd[1]);
				Out.ar(aoBusIcontact, qd[2]);
			}
		).add(libname);

		/////////////////////////////////////////////////////////////////////////
		// HRFegg SynthDef
		// This Synth simply computes the difference between L0 and L(1..N).sum
		/////////////////////////////////////////////////////////////////////////

		SynthDef(nameHRFEGG,
			{ | aiBusGateDFT,
				aiBusAmplitudeFirst,
				aoBusHRFegg |
				var level1g, levelHg, hrf;
				var level1 = In.ar(aiBusAmplitudeFirst);			// Level of EGG fundamental in Bels
				var levelH = In.ar(aiBusAmplitudeFirst+nHarmonics);	// Level of summed harmonics > #1

				// Grab gate
				var gc   = In.ar(aiBusGateDFT);

				// Get the values at the trigger
				level1g = Latch.ar(level1, gc);
				levelHg = Latch.ar(levelH, gc);
				hrf = (levelHg - level1g) * 10.0; 	// difference, back to deciBels
				Out.ar(aoBusHRFegg,  [hrf]);
			}
		).add(libname);

/*		/////////////////////////////////////////////////////////////////////////
		//   PROBABLY NOT: experimental diplophonia detector
		/////////////////////////////////////////////////////////////////////////

		SynthDef(nameDiplo,
			{ | aiBusConditionedEGG,
				aiBusGateCycle,
				aiBusAmplitudeFirst,
				aoBusAmplitudeDiplo |

				var in, inL0, gcycle, gDFT, gSkipped, length, gLength;
				var amp, dipl, res, complexAbs;

				in = In.ar(aiBusConditionedEGG);
				inL0 = In.ar(aiBusAmplitudeFirst);
				gcycle = PulseDivider.ar(In.ar(aiBusGateCycle), 2);

				// Perform the DFT calculations for each cycle marked by gate3
				// Ignores DFT cycles that are too long/short. Using default with a minimum of 10 samples
				// and a minimum of 50 cycles/s (typically equates to at most 882 samples)
				#gDFT, gSkipped, length ...res = DFT2.ar(in, gcycle, 1, minFrequency, minSamples);
				gLength = Gate.ar(length, gDFT);   // DFT2 outputs zeros most of the time
				complexAbs = Complex(res[0], res[1]).abs * (gLength.reciprocal);
				dipl = MulAdd(complexAbs.ampdb, 0.1, inL0.neg);

				// Median-filter to suppress spurious peaks
				dipl = MedianTriggered.ar(dipl, gDFT, 5);
				Out.ar(aoBusAmplitudeDiplo, Gate.ar(dipl, gDFT));
			}
		).add(libname);  */

	} /* compile */


/*	////// DEPRECATED /////////////////
	*peakFollower { |
		aiBusConditionedEGG, // The conditioned EGG
		aoBusGate, 			 // The output gate, open when a new cycle begins
		coBusEGGvalid		 // dummy arg
		...args |

		^Array.with(namePeakFollower,
			[
				\aiBusConditionedEGG, aiBusConditionedEGG,
				\aoBusGate, aoBusGate
			],
			*args
		);
	} */

	*phasePortrait { |
		aiBusConditionedEGG, // The conditioned EGG
		aoBusGate, 			 // The output gate, open when a new cycle begins
		coBusEGGvalid		 // dummy no-op arg
		...args |

		^Array.with(namePhasePortrait,
			[
				\aiBusConditionedEGG, aiBusConditionedEGG,
				\aoBusGate, aoBusGate,
				\coBusEGGvalid, coBusEGGvalid
			],
			*args
		);
	}

	*phasePortrait2 { |
		aiBusConditionedEGG, // The conditioned EGG
		aoBusGate, 			 // The output gate, open when a new cycle begins
		coBusEGGvalid		 // High when the EGG signal is "valid"
		...args |

		^Array.with(namePhasePortrait2,
			[
				\aiBusConditionedEGG, aiBusConditionedEGG,
				\aoBusGate, aoBusGate,
				\coBusEGGvalid, coBusEGGvalid
			],
			*args
		);
	}

	*nDFTs { |
		aiBusConditionedEGG, // The conditioned EGG signal
		aiBusGateCycle, // The gate that marks when a new cycle begins
		aoBusGateDFT, // The output gate for when DFT data is available
		aoBusGateDelayedCycle, // The output gate when DFT data is available, or a cycle got skipped
		aoBusAmplitudeFirst, // The first of nHarmonics consecutive output buses for the amplitudes
		aoBusPhaseFirst // The first of nHarmonics consecutive output buses for the phases
		...args |

		^Array.with(nameNDFTs,
			[
				\aiBusConditionedEGG, aiBusConditionedEGG,
				\aiBusGateCycle, aiBusGateCycle,
				\aoBusGateDFT, aoBusGateDFT,
				\aoBusGateDelayedCycle, aoBusGateDelayedCycle,
				\aoBusAmplitudeFirst, aoBusAmplitudeFirst,
				\aoBusPhaseFirst, aoBusPhaseFirst
			],
			*args
		);
	}

	*dftFilters { |
		aiBusGateDFT,
		aiBusGateCycle,
		aiBusGateDelayedCycle,
		ciBusClarity,
		ciBusEGGvalid,
		aoBusGateFilteredDFT
		...args |

		^Array.with(nameDFTFilters,
			[
				\aiBusGateDFT, aiBusGateDFT,
				\aiBusGateCycle, aiBusGateCycle,
				\aiBusGateDelayedCycle, aiBusGateDelayedCycle,
				\ciBusClarity, ciBusClarity,
				\ciBusEGGvalid, ciBusEGGvalid,
				\aoBusGateFilteredDFT, aoBusGateFilteredDFT
			],
			*args
		);
	}

	*qciDEGG { |
		aiBusConditionedEGG,
		aiBusGateCycle,
		aiBusGateDelayedCycle,
		aoBusDEGGmax,
		aoBusQcontact,
		aoBusIcontact
		...args |

		^Array.with(nameQciDEGG,
			[
				\aiBusConditionedEGG, aiBusConditionedEGG, // The conditioned EGG signal
				\aiBusGateCycle, aiBusGateCycle, // The gate that marks when a new cycle begins
				\aiBusGateDelayedCycle, aiBusGateDelayedCycle,
				\aoBusDEGGmax, aoBusDEGGmax,
				\aoBusQcontact, aoBusQcontact,
				\aoBusIcontact, aoBusIcontact
			],
			*args
		);
	}

	*hrfEGG { |
		aiBusGateDFT,
		aiBusAmplitudeFirst,
		aoBusHRFegg
		...args |

		^Array.with(nameHRFEGG,
			[
				\aiBusGateDFT, aiBusGateDFT,
				\aiBusAmplitudeFirst, aiBusAmplitudeFirst,
				\aoBusHRFegg, aoBusHRFegg,
			],
			*args
		);
	}

/*	*diplo { |
		aiBusConditionedEGG,
		aiBusGateCycle,
		aiBusAmplitudeFirst,
		aoBusAmplitudeDiplo
		...args |

		^Array.with(nameDiplo,
			[
				\aiBusConditionedEGG, aiBusConditionedEGG, // The conditioned EGG signal
				\aiBusGateCycle, aiBusGateCycle, // The gate that marks when a new cycle begins
				\aoBusAmplitudeFirst, aiBusAmplitudeFirst,
				\aoBusAmplitudeDiplo, aoBusAmplitudeDiplo
			],
			*args
		);
	}  */
}