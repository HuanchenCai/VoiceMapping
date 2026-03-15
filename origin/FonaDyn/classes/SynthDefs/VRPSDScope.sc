// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
VRPSDScope {

	classvar namePrepare = \sdPrepareScope;
	classvar nameMovingEGG = \sdMovingEGG;

	*compile { | libname, movingEGGCount, minSamples, maxSamples, normalize |
		movingEGGCount = movingEGGCount.asInteger;
		minSamples = minSamples.asInteger;
		maxSamples = maxSamples.asInteger;
		normalize = normalize.asInteger;

		SynthDef(namePrepare,
			{ | aoBusTimestamp |
				Out.ar(aoBusTimestamp, [ Timestamp.ar ]);
			}
		).add(libname);

		SynthDef(nameMovingEGG,
			{ | aiBusGateCycle,
				aiBusEGG,
				oBuffer |

				var in = In.ar(aiBusEGG);
				var gate = In.ar(aiBusGateCycle);
				MovingEGG.ar(oBuffer, in, gate, movingEGGCount, minSamples, maxSamples, normalize);
			}
		).add(libname);
	}

	*prepare { | aoBusTimestamp ...args |
		^Array.with(namePrepare,
			[
				\aoBusTimestamp, aoBusTimestamp
			],
			*args
		);
	}

	*movingEGG { |
		aiBusGateCycle,
		aiBusEGG,
		oBuffer
		...args |

		^Array.with(nameMovingEGG,
			[
				\aiBusGateCycle, aiBusGateCycle,
				\aiBusEGG, aiBusEGG,
				\oBuffer, oBuffer
			],
			*args
		);
	}
}