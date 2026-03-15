// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPSDSampEn {
	classvar nameSampEn = \sdSampEn;

	*compile { |
		libname,
		amplitudeWindowSize, amplitudeHarmonics, amplitudeSequenceLength, amplitudeTolerance,
		phaseWindowSize, phaseHarmonics, phaseSequenceLength, phaseTolerance |

		amplitudeWindowSize = amplitudeWindowSize.asInteger;
		amplitudeHarmonics = amplitudeHarmonics.asInteger;
		amplitudeSequenceLength = amplitudeSequenceLength.asInteger;

		phaseWindowSize = phaseWindowSize.asInteger;
		phaseHarmonics = phaseHarmonics.asInteger;
		phaseSequenceLength = phaseSequenceLength.asInteger;

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// SampEn SynthDef
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameSampEn,
			{ | aiBusAmplitudeFirst, // Input bus for the amplitude values.
				aiBusPhaseFirst, // Input bus for the phase values.
				aiBusGateDFT, // Gate for when new DFT data is available through aiBusAmplitudeFirst & aiBusPhaseFirst.
				aoBusSampEn | // Output bus for the SampEn measurement.

				var aSEAmps, aSEPhases;
				var aBusAmps, aBusPhases;
				var aSE;
				var gate;

				// Fetch the data from the input buses
				// Appending .asArray in case there is just one of either
				gate = In.ar(aiBusGateDFT);
				aBusAmps = In.ar(aiBusAmplitudeFirst, amplitudeHarmonics).asArray;
				aBusPhases = In.ar(aiBusPhaseFirst, phaseHarmonics).abs.asArray;

				// For each input bus: perform the necessary Sample Entropy calculations.
				aSEAmps = aBusAmps collect: { | bus | SampleEntropyFromBus.ar(bus, amplitudeWindowSize, amplitudeSequenceLength, amplitudeTolerance, gate) };
				aSEPhases = aBusPhases collect: { | bus | SampleEntropyFromBus.ar(bus, phaseWindowSize, phaseSequenceLength, phaseTolerance, gate) };

				// Sum up the result, and post it on the output bus.
				aSE = (aSEAmps ++ aSEPhases).sum;
				Out.ar(aoBusSampEn, [aSE]);
			}
		).add(libname);
	}

	*sampEn {
		| aiBusAmplitudeFirst, // Control rate input bus for the amplitude values.
		  aiBusPhaseFirst, // Control rate input bus for the phase values.
		  aiBusGateDFT, // Gate for when new DFT data is available through aiBusAmplitudeFirst & aiBusPhaseFirst.
		  aoBusSampEn // Control rate output bus for the SampEn measurement.
		  ... args |

		^Array.with(nameSampEn,
			[
				\aiBusAmplitudeFirst, aiBusAmplitudeFirst,
				\aiBusPhaseFirst, aiBusPhaseFirst,
				\aiBusGateDFT, aiBusGateDFT,
				\aoBusSampEn, aoBusSampEn
			],
			*args
		);
	}
}