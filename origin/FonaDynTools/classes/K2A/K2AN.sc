// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
K2AN : UGen {
	*ar {
		| in = 0 |
		^this.multiNew('audio', in);
	}
}