// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
VRPSDCluster {
	classvar nameNCluster = \sdNCluster;
	classvar nameNClusterNoReset = \sdNClusterNoReset;
	classvar nameGeneratePoints = \sdGeneratePoints;
	classvar nameSmoothedClusterCycle = \sdSmoothedClusterCycle;

	*compile { | libname, nClusters, nHarmonics, learn, minSamples, maxSamples, smoothFactor |

		nHarmonics = nHarmonics.asInteger;
		nClusters = nClusters.asInteger;
		learn = learn.asInteger;
		minSamples = minSamples.asInteger;
		maxSamples = maxSamples.asInteger;

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// SynthDef that generates all points
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameGeneratePoints,
			{ | aiBusAmplitudeFirst, // The first of nHarmonics consecutive buses with DFT amplitudes
				aiBusPhaseFirst, // The first of nHarmonics consecutive buses with DFT phases
				aoBusDeltaAmplitudeFirst, // The first of nHarmonics consecutive output buses for delta amplitudes
				aoBusDeltaPhaseFirst | // The first of nHarmonics consecutive output buses for delta phases

				var amps, phases, delta_amps, delta_phases;
				var scaledL0;

				amps = In.ar(aiBusAmplitudeFirst, nHarmonics);  // Skip the last one
				phases = In.ar(aiBusPhaseFirst, nHarmonics+1);

				// Compute all level deltas relative to the 1st term
				delta_amps   = MulAdd(amps[0],  -1, amps[1..(nHarmonics-1)]);
				delta_amps = delta_amps.add(amps[0]); 			// Replace the last one

				delta_phases = MulAdd(phases[0], -1, phases[1..nHarmonics]);


				Out.ar(aoBusDeltaAmplitudeFirst, delta_amps);
				Out.ar(aoBusDeltaPhaseFirst, delta_phases);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// N Cluster SynthDef
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameNCluster,
			{ | iBufferKMeansRT, // The buffer used by KMeansRT
				aiBusDeltaAmplitudeFirst, // The first of nHarmonics consecutive output buses for delta amplitudes
				aiBusDeltaPhaseFirst, // The first of nHarmonics consecutive output buses for delta phases
				aiBusGate, // Gate for when new DFT data is available through aiBusDeltaAmplitudeFirst and aiBusDeltaPhaseFirst
				ciBusEGGvalid, // High if EGG data are valid
				ciBusReset, // Reset once this becomes active (start over with learning)
				aoBusClusterNumber | // The output bus for the cluster number

				var delta_amps, delta_phases, scales;
				var scaledAmps, scaledCosines, scaledSines;
				var aIndex, gate, count;
				var reset, resetArmed;

				count = nHarmonics;
				delta_amps = In.ar(aiBusDeltaAmplitudeFirst, count);
				delta_phases = In.ar(aiBusDeltaPhaseFirst, count);
				gate = In.ar(aiBusGate) * K2AN.ar(In.kr(ciBusEGGvalid));
				reset = In.kr(ciBusReset);

				// Scale down the fundamental only
				// so that it does not affect the clustering.
				// (The compiler should optimize out the Muls by 1.0)
				scales = 1.0 ! (count-1) ++ 0.001;
				scaledAmps 	  = MulAdd(delta_amps, scales);
				scaledCosines = MulAdd(delta_phases.cos, scales);
				scaledSines   = MulAdd(delta_phases.sin, scales);

				// The Gate.ar here should not be needed, according to the doc for KMeansRTv2...
				aIndex = Gate.ar(KMeansRTv2.ar(iBufferKMeansRT, scaledAmps ++ scaledCosines ++ scaledSines, nClusters, gate, reset, learn), gate);
				Out.kr(ciBusReset, [0]); // Reset the reset flag, so we don't keep on resetting every control period
				Out.ar(aoBusClusterNumber, [aIndex]);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// N Cluster No Reset SynthDef
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameNClusterNoReset,
			{ | iBufferKMeansRT, // The buffer used by KMeansRT
				aiBusDeltaAmplitudeFirst, // The first of nHarmonics consecutive output buses for delta amplitudes
				aiBusDeltaPhaseFirst, // The first of nHarmonics consecutive output buses for delta phases
				aiBusGate, // Gate for when new DFT data is available through aiBusDeltaAmplitudeFirst and aiBusDeltaPhaseFirst
				aoBusClusterNumber | // The output bus for the cluster number

				var delta_amps, delta_phases, scales;
				var scaledAmps, scaledCosines, scaledSines;
				var aIndex, gate, count;

				count = nHarmonics;
				scaledCosines = Array.new(count);
				scaledSines = Array.new(count);

				delta_amps = In.ar(aiBusDeltaAmplitudeFirst, count);
				delta_phases = In.ar(aiBusDeltaPhaseFirst, count);
				gate = In.ar(aiBusGate);

				// Scale down the fundamental only
				// so that it does not affect the clustering.
				// (The compiler should optimize out the Muls by 1.0)
				scales = 1.0 ! (count-1) ++ 0.001;
				scaledAmps 	  = MulAdd(delta_amps, scales);
				scaledCosines = MulAdd(delta_phases.cos, scales);
				scaledSines   = MulAdd(delta_phases.sin, scales);

				// The Gate.ar here should not be needed, according to the doc for KMeansRTv2...
				aIndex = Gate.ar(KMeansRTv2.ar(iBufferKMeansRT, scaledAmps ++ scaledCosines ++ scaledSines, nClusters, gate, 0, learn), gate);
				Out.ar(aoBusClusterNumber, [aIndex]);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// SmoothedClusterCycle
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameSmoothedClusterCycle,
			{ | aiBusEGG,
				aiBusGateCycle,
				aiBusGateFilteredDFT,
				aiBusClusterNumber,
				oBuffer |

				var egg = In.ar(aiBusEGG);
				var gateCycle = In.ar(aiBusGateCycle);
				var gateFilteredDFT = In.ar(aiBusGateFilteredDFT);
				var clusterNumber = In.ar(aiBusClusterNumber);

				SmoothedClusterCycle.ar(
					oBuffer, // Required for output
					egg, // Required to grab the cycle data
					gateCycle, // Required to split the EGG signal into cycles
					gateFilteredDFT, // Required to know which cycles were discarded
					clusterNumber, // Required to know which cluster this cycle belongs to
					nClusters, minSamples, maxSamples, smoothFactor); // Constants
			}
		).add(libname);
	}

	*generatePoints { |
		aiBusAmplitudeFirst, // The first of nHarmonics+1 consecutive buses with DFT amplitudes
		aiBusPhaseFirst, // The first of nHarmonics+1 consecutive buses with DFT phases
		aoBusDeltaAmplitudeFirst, // The first of nHarmonics consecutive output buses for delta amplitudes
		aoBusDeltaPhaseFirst // The first of nHarmonics consecutive output buses for delta phases
		...args |

		^Array.with(nameGeneratePoints,
			[
				\aiBusAmplitudeFirst, aiBusAmplitudeFirst,
				\aiBusPhaseFirst, aiBusPhaseFirst,
				\aoBusDeltaAmplitudeFirst, aoBusDeltaAmplitudeFirst,
				\aoBusDeltaPhaseFirst, aoBusDeltaPhaseFirst,
			],
			*args
		);
	}

	*nClusters { |
		iBufferKMeansRT, // The buffer used by KMeansRT
		aiBusDeltaAmplitudeFirst, // The first of nHarmonics consecutive output buses for delta amplitudes
		aiBusDeltaPhaseFirst, // The first of nHarmonics consecutive output buses for delta phases
		aiBusGate, // Gate for when new DFT data is available through aiBusDeltaAmplitudeFirst and aiBusDeltaPhaseFirst
		ciBusEGGvalid, // The bus that signals when phonation via EGG is active
		ciBusReset, // The bus with the reset input for the KMeansRT UGen.
		aoBusClusterNumber // The output bus for the cluster number
		...args |

		^Array.with(nameNCluster,
			[
				\iBufferKMeansRT, iBufferKMeansRT,
				\aiBusDeltaAmplitudeFirst, aiBusDeltaAmplitudeFirst,
				\aiBusDeltaPhaseFirst, aiBusDeltaPhaseFirst,
				\aiBusGate, aiBusGate,
				\ciBusEGGvalid, ciBusEGGvalid,
				\ciBusReset, ciBusReset,
				\aoBusClusterNumber, aoBusClusterNumber
			],
			*args
		);
	}

/*	*nClustersNoReset { |
		iBufferKMeansRT, // The buffer used by KMeansRT
		aiBusDeltaAmplitudeFirst, // The first of nHarmonics consecutive output buses for delta amplitudes
		aiBusDeltaPhaseFirst, // The first of nHarmonics consecutive output buses for delta phases
		aiBusGate, // Gate for when new DFT data is available through aiBusDeltaAmplitudeFirst and aiBusDeltaPhaseFirst
		aoBusClusterNumber // The output bus for the cluster number
		...args |

		^Array.with(nameNClusterNoReset,
			[
				\iBufferKMeansRT, iBufferKMeansRT,
				\aiBusDeltaAmplitudeFirst, aiBusDeltaAmplitudeFirst,
				\aiBusDeltaPhaseFirst, aiBusDeltaPhaseFirst,
				\aiBusGate, aiBusGate,
				\aoBusClusterNumber, aoBusClusterNumber
			],
			*args
		);
	}
*/

	*smoothedClusterCycle { |
		aiBusEGG,
		aiBusGateCycle,
		aiBusGateFilteredDFT,
		aiBusClusterNumber,
		oBuffer
		...args |

		^Array.with(nameSmoothedClusterCycle,
			[
				\aiBusEGG, aiBusEGG,
				\aiBusGateCycle, aiBusGateCycle,
				\aiBusGateFilteredDFT, aiBusGateFilteredDFT,
				\aiBusClusterNumber, aiBusClusterNumber,
				\oBuffer, oBuffer
			],
			*args
		);
	}

}