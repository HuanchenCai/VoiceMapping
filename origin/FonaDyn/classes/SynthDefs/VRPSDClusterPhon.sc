// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPSDClusterPhon {
	classvar namePhonNCluster = \sdPhonNCluster;
	classvar namePhonNClusterNoReset = \sdPhonNClusterNoReset;
	classvar namePhonGeneratePoints = \sdPhonGeneratePoints;

	*compile { | libname, nClusters, nMetrics, learn, busTable |

		nMetrics = nMetrics.asInteger;
		nClusters = nClusters.asInteger;
		learn = learn.asInteger;

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// SynthDef that rescales the selected phonation metrics prior to clustering
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(namePhonGeneratePoints,
			{ | coBusMetricFirst |  // The first of nMetrics consecutive output buses for scaled values
				var scaled_mags = [];

				// mVec[2] contains the bus number,
				// mVec[3] is an array of 'linlin'/'explin' msgs, each with 5 arguments
				scaled_mags = busTable.collect ({ | mVec, i|
					if (mVec[1] == \audio,
						{ In.ar(mVec[2], 1).performMsg(mVec[3]) },
						{ In.kr(mVec[2], 1).performMsg(mVec[3]) }
					)
				});

				// Do we need a smoothing filter here?
				Out.kr(coBusMetricFirst, scaled_mags);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// N Cluster SynthDef
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		// The phonation type clustering is processed at control rate
		//   (EGG clustering is at audio rate).
		// If several EGG cycles occur in a control period,
		// only the first one will trigger the phonation type clustering.
		// This happens only for fundamental frequencies > 700 Hz
		SynthDef(namePhonNCluster,
			{ | iBufferKMeansRT, 			// The buffer used by KMeansRT
				aiBusGateFilteredDFT,		// open once on each EGG cycle
				ciBusEGGvalid,				// High if EGG data are valid
				ciBusScaledMetricFirst, 	// The first of nMetrics consecutive buses for scaled metric values
				ciBusReset,					// Reset once this becomes active (start over with learning)
				coBusPhonClusterNumber | 	// The output bus for the cluster number

				var scaled_mags;
				var cIndex, gate, count;
				var reset;

				count = nMetrics;
				gate = T2K.kr(In.ar(aiBusGateFilteredDFT)) * In.kr(ciBusEGGvalid);
				scaled_mags = In.kr(ciBusScaledMetricFirst, count);
				reset = In.kr(ciBusReset);

				cIndex = Gate.kr(KMeansRTv2.kr(iBufferKMeansRT, scaled_mags, nClusters, gate, reset, learn), gate);
				Out.kr(ciBusReset, [0]); // Reset the reset flag, so we don't keep on resetting every control period
				Out.kr(coBusPhonClusterNumber, [cIndex]);
			}
		).add(libname);
	}

	*generatePoints { |
		coBusMetricFirst   // The first of nMetrics consecutive output buses for scaled values
		...args |

		^Array.with(namePhonGeneratePoints,
			[
				\coBusMetricFirst, coBusMetricFirst
			],
			*args
		);
	}

	*nPhonClusters { |
		iBufferKMeansRT, // The buffer used by KMeansRT
		aiBusGateFilteredDFT,
		ciBusEGGvalid,
		ciBusScaledMetricFirst, // The first of nMetrics consecutive output buses for scaled metric values
		ciBusReset, // The bus with the reset input for the KMeansRTv2 UGen.
		coBusClusterNumber // The output bus for the cluster number
		...args |

		^Array.with(namePhonNCluster,
			[
				\iBufferKMeansRT, iBufferKMeansRT,
				\aiBusGateFilteredDFT, aiBusGateFilteredDFT,
				\ciBusEGGvalid, ciBusEGGvalid,
				\ciBusScaledMetricFirst, ciBusScaledMetricFirst,
				\ciBusReset, ciBusReset,
				\coBusPhonClusterNumber, coBusClusterNumber
			],
			*args
		);
	}
}