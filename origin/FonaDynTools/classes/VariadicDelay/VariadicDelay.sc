// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
VariadicDelay : UGen {
	*ar { | in, ingate, outgate, bufsize |
		^this.multiNew('audio', in, ingate, outgate, bufsize);
	}

	*kr { | in, ingate, outgate, bufsize |
		^this.multiNew('control', in, ingate, outgate, bufsize);
	}
}