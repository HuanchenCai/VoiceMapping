// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
PeakProminence : MultiOutUGen {
	*new { | buffer, lowBin = 0, highBin=511, todB=1 |
		^this.kr(buffer, lowBin, highBin)
	}

	*kr { | buffer, lowBin = 0, highBin=511, todB=1 |
		^this.multiNew('control', buffer, lowBin, highBin, todB)
	}

	init { | ... theInputs | //Required for MultiOutUgen
		inputs = theInputs;
		^this.initOutputs(5, \control); // pp + slope + intercept + maxpp + maxix
	}
}