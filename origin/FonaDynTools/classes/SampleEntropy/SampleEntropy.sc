// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
SampleEntropyFromBuffer : UGen {
	*ar {
		| bufnum = 0, sequence_length = 2, tolerance = 1, phase = 0, length = -1 |
		^this.multiNew('audio', bufnum, sequence_length, tolerance, phase, length);
	}

	*kr {
		| bufnum = 0, sequence_length = 2, tolerance = 1, phase = 0, length = -1 |
		^this.multiNew('control', bufnum, sequence_length, tolerance, phase, length);
	}

	*upperBounds { | buffer, sequence_length |
		^SampleEntropyFromBus.upperBounds(buffer.numFrames, sequence_length);
	}
}

SampleEntropyFromBus : UGen {
	*ar {
		| in, window_size = 20, sequence_length = 3, tolerance = 1, gate = 1 |
		^this.multiNew('audio', in, window_size, sequence_length, tolerance, gate);
	}

	*kr {
		| in, window_size = 20, sequence_length = 3, tolerance = 1, gate = 1 |
		^this.multiNew('control', in, window_size, sequence_length, tolerance, gate);
	}

	*upperBounds { | window_size, sequence_length |
		// This is only an approximation of the largest possible sample entropy
		// given the window size and sequence length. This approximation is fairly good for
		// small window sizes, but gets increasingly poor with larger window sizes.
		var n = window_size;
		var m = sequence_length;
		var m1 = m + 1;
		var nm = n - m;
		var ret = nm;
		for (1, nm - 1, { | i | ret = ret + floor( (nm - i) / m1 ) } );
		^log(ret);
	}
}