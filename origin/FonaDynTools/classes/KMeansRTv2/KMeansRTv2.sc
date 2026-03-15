// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
KMeansRTv2 : UGen {

	*allocBuffer { | server, nDimensions, nClusters, initType = \zero ...args |
		var buf = Buffer(server, nClusters, nDimensions + 1);

		switch (initType,
			\zero, { // Zero out the buffer
				buf.alloc; // "Allocates zero filled buffer to number of channels and samples."
			},

			\set, { // Set the buffer to the matrix specificed in args[0]
				var matrix = args[0].flat;
				if (matrix.size != (buf.numChannels * buf.numFrames), {
					Error("Bad matrix size for \\set").throw;
				});

				buf.alloc( buf.setnMsg(0, matrix) );
			},

			{ Error("Bad initType!").throw; }
		);

		^buf;
	}

	*ar { | bufnum, inputdata, nClusters=5, gate=1, reset=0, learn=1 |
		inputdata = inputdata.asArray;
		^this.multiNew('audio', bufnum, nClusters, gate, reset, learn, *inputdata);
	}

	*kr { | bufnum, inputdata, nClusters=5, gate=1, reset=0, learn=1 |
		inputdata = inputdata.asArray;
		^this.multiNew('control', bufnum, nClusters, gate, reset, learn, *inputdata)
	}

	*arGetCentroid { | bufnum, classif, nDimensions |
		^BufRd.ar(nDimensions + 1, bufnum, classif, interpolation: 1)[..nDimensions-1];
	}

	*krGetCentroid { | bufnum, classif, nDimensions |
		^BufRd.kr(nDimensions + 1, bufnum, classif, interpolation: 1)[..nDimensions-1];
	}
}