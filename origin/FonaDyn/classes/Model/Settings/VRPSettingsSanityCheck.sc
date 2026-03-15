// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
//
// Addition of a sanity check for some settings.
// May help to contain all the sanityChecks in the same file,
//	 instead of small checks in each individual settings file.
//

+ VRPSettings {
	sanityCheck {
		var ret = true;

		ret = csdft.sanityCheck(this);
		ret = ret and: { io.sanityCheck(this) };
		^ret;
	}
}

+ VRPSettingsCSDFT {
	sanityCheck { | settings |
		var ret = true;
		var tmpHarm =
		[
			settings.cluster.nHarmonics,
			settings.plots.amplitudeHarmonics,
			settings.plots.phaseHarmonics
		].maxItem.asInteger;

		if (tmpHarm != nHarmonics, {
			format("Harmonics count mismatch: nHarmonics=%, needed=%", nHarmonics, tmpHarm).error;
			nHarmonics = tmpHarm;
			settings.cluster.nHarmonics = tmpHarm;
			ret = false;
		});

		^ret;
	}
}

+ VRPSettingsIO {
	sanityCheck { | settings |
		var retVal = true;
		var ios = settings.io;
		var nChannels, nSampleFormat, sf;
		var bSingerMode = (VRPDataVRP.nMaxSPL > 120);

		if (ios.inputType == VRPSettingsIO.inputTypeFile(), {
			// Protest if the specified input file does not exist
			if (File.exists(ios.filePathInput).not,
				{
					format("Not found: file %", ios.filePathInput.tr($\\, $/)).error;
					^false;
				}
			);

			// Protest if the input file is mono
			sf = SoundFile.new;
			sf.openRead(settings.io.filePathInput);
			nChannels = sf.numChannels;
			nSampleFormat = sf.sampleFormat;
			sf.close;
			if (nChannels < 2,
				{
					format("File %\n   has only one channel; at least two are needed.", ios.filePathInput.tr($\\, $/)).error;
					^false;
				}
			);

			// Check if we are analyzing a 16-bit file, and if so inhibit singerMode
			if (bSingerMode, {
				// Is the file's word length 16 or 24 bits?
				if (nSampleFormat == "int16", { AppClock.sched(0.01, {
						var fn = PathName(ios.filePathInput).fileName;
						format("% is a 16-bit file: switching to 120 dB max SPL", fn).warn;
						this.changed(this, \splRangeChanged, false);
				})});
			});
		});

		// Protest if we are about to overwrite the source signal when re-recording
		if (ios.enabledWriteAudio.asBoolean
			and: { ios.inputType == VRPSettingsIO.inputTypeFile() }
			and: { ios.keepInputName }
			and: { PathName(ios.filePathInput).pathOnly.asString.tr($\\, $/).beginsWith(settings.io.outDir) },
			{
				"To avoid overwriting signals, choose another output directory, or uncheck \"Keep input file name\".".error;
				retVal = false;
			}
		);

		^retVal;
	}
}
