// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPSettingsIO {
	// States
	var <>inputType; // One of the inputType*s below.
	var <>enabledEcho; // True if the recorded voice or playback voice should be echoed through the speakers
	var <>enabledEGGlisten; // True if 2nd channel should play EGG instead of Voice
	var <>enabledWriteLog; // True if a log should be written
	var <writeLogFrameRate; // 0 means cycle-synchronous, otherwise Hz for isochronous frames (100..500 Hz recommended)
	var <>enabledWriteAudio; // True if the voice/EGG data should be written to a file
	var <>enabledWriteCycleDetection; // True if the cycle detection data should be written to a file
	// var <>enabledWriteOutputPoints; // True if the points used for clustering should be output to a file
	// var <>enabledWriteSampEn; // True if the SampEn values should be output to a file
	var <>enabledWriteGates; // True if a _Gates file should be written
	var <>arrayRecordInputs;
	var <>enabledRecordExtraChannels;
	var <>arrayRecordExtraInputs;
	var <>rateExtraInputs;
	var <>nInChannelCount;  // Do not change this from a script

	var <>filePathInput; 	// The path to the input file
	var <>fileDuration;
	var <>outDir;			// The path to the output directory
	var <>keepInputName;
	var <>keepData;      	// Save current cluster & VRP data for next start

	classvar <inputTypeFile = 1; // Input is taken from a file.
	classvar <inputTypeRecord = 2; // Input is a live recording.
	classvar <inputTypeScript = 3; // Input is a text script

	*new {
		^super.new.init;
	}

	init {
		writeLogFrameRate = 0;	// cycle-synchronous frames
		enabledEGGlisten = false;
		enabledWriteGates = false;
		enabledWriteAudio = false;
		enabledWriteLog = false;
		enabledRecordExtraChannels = false;
		arrayRecordInputs = [VRPControllerIO.audioInputBusIndexVoice, VRPControllerIO.audioInputBusIndexEGG];
		arrayRecordExtraInputs = nil;
		rateExtraInputs = 100;  // default to 100 Hz
 		keepInputName = true;
		keepData = false;
		nInChannelCount = 2;
	}

	writeLogFrameRate_ { | lfr |
		writeLogFrameRate = lfr;
	}
}
