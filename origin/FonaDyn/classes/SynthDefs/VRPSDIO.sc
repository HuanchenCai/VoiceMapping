// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPSDIO {
	classvar nameLiveInput = \sdLiveInput;			// deprecated
	classvar nameLiveInput2 = \sdLiveInput2;
	classvar nameDiskInput = \sdDiskInput;			// deprecated
	classvar nameDiskInput2 = \sdDiskInput2;		// deprecated
	classvar nameDiskInput3 = \sdDiskInput3;
	classvar nameDiskInput4 = \sdDiskInput4;		// TEST ONLY of Voice-EGG correlation
	classvar nameEchoMicrophone = \sdEchoMicrophone;
	classvar nameWriteAudio = \sdWriteAudio;
	classvar nameWriteCycleDetectionLog = \sdWriteCycleDetectionLog;
	classvar nameWritePoints = \sdWritePoints;
	classvar nameWriteSampEn = \sdWriteSampEn;
	classvar nameWriteFreqAmp = \sdWriteFrequencyAmplitude;
	classvar nameWriteLog = \sdWriteLog;
	classvar nameWriteGates = \sdWriteGates;
	classvar nameRecordExtraChannels = \sdRecordExtraChannels;
	// const <rateExtra = 100.0;

	/* FIR filter additions	*/
	classvar lpBuffer = nil;
	classvar hpBuffer = nil;
	classvar bpBuffer = nil;

	// List of parameter arrays for optional notch filters
	classvar <preFilters;			 // array of [freq, dB, q] triplets
	classvar <postFilters;			 // array of [freq, -dB, -q] triplets

	// For Matlab: enumerate the logfile base-track contents
	classvar <namesArray = #[
		"fo (ST)",
		"SL (dBFS)",
		1,  //	VRPSettings.iClarity
		2, 	//	VRPSettings.iCrestFactor
		3,  //	VRPSettings.iSpecBal
		4,	//	VRPSettings.icppSmoothed
		"cEGG #",
		"cPhon #",
		5,	//	VRPSettings.iEntropy
		8,	//	VRPSettings.iIcontact
		6,	//	VRPSettings.idEGGmax
		7	//	VRPSettings.iQcontact
	];


	*initClass {
		preFilters = [];
		postFilters = [];
	}

	*loadCoeffs {
		var lpCoeffs, hpCoeffs, bpCoeffs;

		/* FIR coeffs generated in Matlab for lowpass @ 10 kHz */
		lpCoeffs = VRPSDIO.getCoeffs(2);
		lpBuffer !? { lpBuffer.free; lpBuffer = nil };
		lpBuffer = Buffer.sendCollection(Server.default, lpCoeffs, 1, -1,
			{ /* |b| (b.numFrames.asInteger.asString + 'lpCoeffs loaded.').postln */ });

		/* FIR coeffs generated in Matlab for highpass @ 100 Hz */
		hpCoeffs = VRPSDIO.getCoeffs(1);
		hpBuffer !? { hpBuffer.free; hpBuffer = nil };
		hpBuffer = Buffer.sendCollection(Server.default, hpCoeffs, 1, -1,
			{ /* |b| (b.numFrames.asInteger.asString + 'hpCoeffs loaded.').postln */ } );

		// FIR coeffs generated in VRPSDIO.getCoeffs for highpass @ 100 Hz plus lowpass @ 10 kHz
		// Needs bufsize=2048
		bpCoeffs = VRPSDIO.getCoeffs(3);
		bpBuffer !? { bpBuffer.free; bpBuffer = nil };
		bpBuffer = Buffer.sendCollection(Server.default, bpCoeffs, 1, -1,
			{ /* |b| (b.numFrames.asInteger.asString + 'bpCoeffs loaded.').postln */ }  );
	}

	// Return a string array in Matlab format that contains the names
	// of the base tracks of the log file (can change with versions)
	*getAllLogMetricNames {
		var outArray;
		outArray = namesArray collect: { | item, i |
			var outstr = "<not set>";
			if (item.class == Integer, {
				VRPSettings.metrics do: { | m, j |
					if (m.class.metricNumber == item, { outstr = m.class.symbol })
				};
			}, {
				outstr = item
			});
			outstr
		};
		^outArray.asCompileString.tr($, , $;)
	}

	*configureEGGfilter { arg params;
		var p;
		if (params.isNil, { ^nil } );
		if (params.isEmpty,
			{
				 preFilters = []; // Remove any current filters
				postFilters = [];
			}, {
				p = params;
				// Specifying a negative Q value means that an additional, inverse filter
				// will be inserted to cancel this filter AFTER the noise thresholding.
				// This is to allow some manipulation also of a tilting noise floor.
				if (params[2] < 0, {
					p[2] = params[2].abs;
					postFilters = postFilters.add([ p[0], p[1].neg, p[2]]);
				});
				preFilters = preFilters.add(p); // else add the given prefilter
			}
		);
		^preFilters.size;
	}

	*compile { | libname, triggerIDEOF, triggerIDClip, mainGroupId, nHarmonics, playEGG=false, logRate=0,
		arrayRecordExtraInputs, rateExtra=100, nInputChannels=2, inScale=1.0, arrRecordChannels, ciBusThreshold |
		this.loadCoeffs;

/*		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Live Input SynthDef without noise reduction, and less delay
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameLiveInput,
			{ | aiBusMic, aiBusEGG, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG |
				var inMic, inEGG, micCond, eggCond, bClip;

				inMic = SoundIn.ar(aiBusMic);       // Get input from a live source
				inEGG = SoundIn.ar(aiBusEGG);

				// Detect when EGG signal is too large
				bClip = PeakFollower.ar(inEGG.abs.madd(1, 0.005), 0.9999) - 1;
				SendTrig.ar(bClip, triggerIDClip, bClip);			    // Tell main about clipping

				micCond = HPF.ar(inMic, 30);				            // HPF +12 db/oct to attenuate rumble
				eggCond = Convolution2.ar(inEGG, hpBuffer.bufnum, 0, 1024);	// HP @100 Hz
				eggCond	= Median.ar(9, eggCond);							// suppress EG2 "crackle"
				eggCond = Convolution2.ar(eggCond, lpBuffer.bufnum, 0, lpBuffer.numFrames);	// LP @10 kHz

				Out.ar(aoBusMic, [inMic]);                              // Feed the raw input to aoBusMic
				Out.ar(aoBusEGG, [inEGG]);                              // Feed the raw input to aoBusEGG
				Out.ar(aoBusConditionedMic, [micCond]);
				Out.ar(aoBusConditionedEGG, [eggCond]);
			}
		).add(libname);
*/
		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Live Input SynthDef with noise reduction (and delay); but no incidental filters
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameLiveInput2,
			{ | aiBusMic, aiBusEGG, ciBusNoiseThreshold, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG |
				var inMic, inEGG, micCond, eggCond, bClip;
				var chain, thresh, bufSize=2048, nDelay=0.034;

				inMic = SoundIn.ar(aiBusMic);       // Get input from a live source
				inEGG = SoundIn.ar(aiBusEGG);

				// Detect when EGG signal is too large
				bClip = PeakFollower.ar(inEGG.abs.madd(1, 0.005), 0.9999) - 1;
				SendTrig.ar(bClip, triggerIDClip, bClip);			    // Tell main about clipping

				micCond = HPF.ar(inMic, 30);				            // HPF +12 db/oct to attenuate rumble

				chain  = FFT(LocalBuf(bufSize, 1), inEGG);
				chain = PV_MagMul(chain, bpBuffer.bufnum);				// bandpass it
				thresh = In.kr(ciBusThreshold); 						// Read from its control bus
				chain  = PV_Compander(chain, thresh, 4.0, 1.0);			// 4.0 is dB-expand ratio below thresh
				eggCond = IFFT.ar(chain);								// EGG will be 46 ms delayed
				micCond = DelayN.ar(micCond, nDelay+0.01, nDelay);		// Keep audio and conditioned EGG in sync

				Out.ar(aoBusMic, [inMic]);                              // Feed the raw input to aoBusMic
				Out.ar(aoBusEGG, [inEGG]);                              // Feed the raw input to aoBusEGG
				Out.ar(aoBusConditionedMic, [micCond]);
				Out.ar(aoBusConditionedEGG, [eggCond]);
			}
		).add(libname);

/*		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Disk Input SynthDef - not currently used
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameDiskInput,
			{ | iBufferDisk, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG |
				var inSignals, inMic, inEGG, micCond, eggCond, eofGate;

				inSignals = DiskIn.ar(nInputChannels, iBufferDisk);
				inMic = inSignals[0] * inScale;
				inEGG = inSignals[1] * inScale;
				// Ignore any remaining input channels

				eofGate = Done.kr(inSignals);			// Add a Done.kr to stop on end-of-file
				SendTrig.kr(eofGate, triggerIDEOF, -1); // Notify about end-of-file
				Pause.kr( 1 - eofGate, mainGroupId ); 	// Pause the main group (all synths)

				micCond = HPF.ar(inMic, 30);				    // HPF +12 db/oct to remove rumble
				eggCond = Convolution2.ar(inEGG, hpBuffer.bufnum, 0, 1024);	// HP @100 Hz
				eggCond	= Median.ar(9, eggCond);								// suppress EG2 "crackle"
				eggCond = Convolution2.ar(eggCond, lpBuffer.bufnum, 0, lpBuffer.numFrames);	// LP @10 kHz

				Out.ar(aoBusMic, [inMic]);                      // Feed the scaled input to aoBusMic
				Out.ar(aoBusEGG, [inEGG]);                      // Feed the raw input to aoBusEGG
				Out.ar(aoBusConditionedMic, [micCond]);
				Out.ar(aoBusConditionedEGG, [eggCond]);
			}
		).add(libname);
*/

/*		////////////////////////////////////////////////////////////////////////////////
		// Disk Input with optional notch filtering and EGG de-noising - not currently used
		////////////////////////////////////////////////////////////////////////////////


		SynthDef(nameDiskInput2,
			{ | iBufferDisk, ciBusNoiseThreshold, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG |
				var inSignals, inMic, inEGG, micCond, eggCond, eofGate;
				var chain, thresh;

				inSignals = DiskIn.ar(nInputChannels, iBufferDisk);
				inMic = inSignals[0] * inScale;
				micCond = HPF.ar(inMic, 30);			// HPF +12 db/oct to remove rumble

				inEGG = inSignals[1] * inScale; 		// Ignore any remaining input channels

				eofGate = Done.kr(inSignals);			// Add a Done.kr to stop on end-of-file
				SendTrig.kr(eofGate, triggerIDEOF, -1); // Notify about end-of-file
				Pause.kr( 1 - eofGate, mainGroupId ); 	// Pause the main group (all synths)

				// Get rid of as much near-DC as possible
				eggCond = Convolution2.ar(inEGG, hpBuffer.bufnum, 0, 1024);	// HP @100 Hz

				/////// Insert zero or more notch filters against stationary stray tones in EGG ///////
				/////// See the documentation for FonaDyn.config(addEGGNotchFilter: [freq, level, Q]).
				notchFilters.do { | p |
					eggCond = BPeakEQ.ar(eggCond, freq: p[0], rq: p[2].reciprocal, db: p[1]);
					format("Applying notch filter to EGG: % Hz, % dB, Q=%", p[0], p[1], p[2]).postln;
				};

				chain  = FFT(LocalBuf(2048, 1), eggCond);
				thresh = In.kr(ciBusThreshold); 				// Read from its control bus
				chain  = PV_Compander(chain, thresh, 4.0, 1.0);	// 4.0 is dB-expand ratio below thresh
				eggCond = IFFT(chain);
//				micCond = DelayN.ar(micCond, 0.075, 0.075);		// Keep audio and EGG in sync

				Out.ar(aoBusMic, [inMic]);                      // Feed the scaled input to aoBusMic
				Out.ar(aoBusEGG, [inEGG]);                      // Feed the raw input to aoBusEGG
				Out.ar(aoBusConditionedMic, [micCond]);
				Out.ar(aoBusConditionedEGG, [eggCond]);
			}
		).add(libname);

*/		////////////////////////////////////////////////////////////////////////////////////
		// Disk Input with optional notch filtering and EGG de-noising.
		// Convolution2 HP-filter is here replaced by scaling down just the first 6 mags
		// in the frequency domain - seems to work well.
		////////////////////////////////////////////////////////////////////////////////////


		SynthDef(nameDiskInput3,
			{ | iBufferDisk, ciBusNoiseThreshold, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG |
				var inSignals, inMic, inEGG, micCond, eggCond, eofGate;
				var chain, thresh, bufSize=2048;
				var nDelay=0.045;   // 2048 samples, minus one control period

				inSignals = DiskIn.ar(nInputChannels, iBufferDisk);
				inMic = inSignals[0] * inScale;
				micCond = HPF.ar(inMic, 30);			// HPF +12 db/oct to suppress rumble

				inEGG = inSignals[1];

				eofGate = Done.kr(inSignals);			// Add a Done.kr to stop on end-of-file
				SendTrig.kr(eofGate, triggerIDEOF, -1); // Notify about end-of-file
				Pause.kr( 1 - eofGate, mainGroupId ); 	// Pause the main group (all synths)

				eggCond = inEGG;

				/////// Insert zero or more notch filters against stationary stray tones in EGG ///////
				/////// See the documentation for FonaDyn.config(addEGGNotchFilter: [freq, level, Q]).
				preFilters.do { | p |
					eggCond = BPeakEQ.ar(eggCond, freq: p[0], rq: p[2].reciprocal, db: p[1]);
					// format("Applying notch filter to EGG: % Hz, % dB, Q=%", p[0], p[1], p[2]).postln;
				};

				chain  = FFT(LocalBuf(bufSize, 1), eggCond);
				chain  = PV_MagMul(chain, bpBuffer.bufnum);		// bandpass it
				thresh = In.kr(ciBusThreshold); 				// Read from its control bus
				chain = PV_Compander(chain, thresh, 4.0, 1.0);	// 4.0 is dB-expand ratio below thresh
				eggCond = IFFT.ar(chain);

				/////// Insert zero or more emphasis filters to cancel one or of the more pre-filters
				/////// AFTER noise thresholding. This is not yet documented.

				postFilters.do { | p |
					eggCond = BPeakEQ.ar(eggCond, freq: p[0], rq: p[2].reciprocal, db: p[1]);
					// format("Applying cancelling post-filter to EGG: % Hz, % dB, Q=%", p[0], p[1], p[2]).postln;
				};

				micCond = DelayN.ar(micCond, nDelay+0.001, nDelay);		// Keep audio and conditioned EGG in sync

				Out.ar(aoBusMic, [inMic]);                      // Feed the scaled input to aoBusMic
				Out.ar(aoBusEGG, [inEGG]);                      // Feed the raw input to aoBusEGG
				Out.ar(aoBusConditionedMic, [micCond]);
				Out.ar(aoBusConditionedEGG, [eggCond]);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameDiskInput4,
			{ | iBufferDisk, ciBusNoiseThreshold, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG, coChainEGGcond |
				var inSignals, inMic, inEGG, micCond, eggCond, eggCrest, eofGate;
				var chain, tapChain, thresh, bufSize=2048;
				var nDelay=0.045;   // 2048 samples, minus one control period
				var chainCopy;

				inSignals = DiskIn.ar(nInputChannels, iBufferDisk);
				inMic = inSignals[0] * inScale;
				micCond = HPF.ar(inMic, 30);			// HPF +12 db/oct to suppress rumble

				inEGG = inSignals[1];

				eofGate = Done.kr(inSignals);			// Add a Done.kr to stop on end-of-file
				SendTrig.kr(eofGate, triggerIDEOF, -1); // Notify about end-of-file
				Pause.kr( 1 - eofGate, mainGroupId ); 	// Pause the main group (all synths)

				eggCond = inEGG;

				/////// Insert zero or more notch filters against stationary stray tones in EGG ///////
				/////// See the documentation for FonaDyn.config(addEGGNotchFilter: [freq, level, Q]).
				preFilters.do { | p |
					eggCond = BPeakEQ.ar(eggCond, freq: p[0], rq: p[2].reciprocal, db: p[1]);
					// format("Applying notch filter to EGG: % Hz, % dB, Q=%", p[0], p[1], p[2]).postln;
				};

				chain  = FFT(LocalBuf(bufSize, 1), eggCond);
				chain  = PV_MagMul(chain, bpBuffer.bufnum);		// bandpass it
				thresh = In.kr(ciBusThreshold); 				// Read from its control bus
				chain = PV_Compander(chain, thresh, 4.0, 1.0);	// 4.0 is dB-expand ratio below thresh
				if (true, {
					chainCopy = PV_Copy(chain, LocalBuf(bufSize));
					Out.kr(coChainEGGcond, [chainCopy]);		// Send this buffer to the cross-correlation
				});
				eggCond = IFFT.ar(chain);

				/////// Insert zero or more emphasis filters to cancel one or of the more pre-filters
				/////// AFTER noise thresholding. This is not yet documented.

				postFilters.do { | p |
					eggCond = BPeakEQ.ar(eggCond, freq: p[0], rq: p[2].reciprocal, db: p[1]);
					// format("Applying cancelling post-filter to EGG: % Hz, % dB, Q=%", p[0], p[1], p[2]).postln;
				};

				micCond = DelayN.ar(micCond, nDelay+0.001, nDelay);		// Keep audio and conditioned EGG in sync

				Out.ar(aoBusMic, [inMic]);                      // Feed the scaled input to aoBusMic
				Out.ar(aoBusEGG, [inEGG]);                      // Feed the raw input to aoBusEGG
				Out.ar(aoBusConditionedMic, [micCond]);
				Out.ar(aoBusConditionedEGG, [eggCond]);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Echo Microphone SynthDef
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		if (playEGG==true, {
			SynthDef(nameEchoMicrophone,
				{ | tDelay, aiBusMic, aiBusEGG, aoBusSpeaker |
					Out.ar(aoBusSpeaker, DelayN.ar([In.ar(aiBusMic), In.ar(aiBusEGG)], 0.2, tDelay));
				}
			).add(libname);
		},{
			SynthDef(nameEchoMicrophone,
				{ | tDelay, aiBusMic, aiBusEGG, aoBusSpeaker |
						Out.ar(aoBusSpeaker, DelayN.ar(In.ar(aiBusMic), 0.2, tDelay) ! 2);
				}
			).add(libname);
		});

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Write Audio SynthDef
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameWriteAudio,
			{ | aiBusMic, aiBusEGG, oBufferAudio |
				var inBuses, outGens, nFirstIn;
				nFirstIn = Server.default.options.numOutputBusChannels;
				inBuses = [aiBusMic, aiBusEGG] ++ (arrRecordChannels[2..] + nFirstIn);
				outGens = inBuses.collect({ |v, i| In.ar(v) });
				GatedDiskOut.ar(oBufferAudio, 1, outGens);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Write the EGG signal and the new cycle markers
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameWriteCycleDetectionLog,
			{ | aiBusEGG, aiBusGateCycle, oBufferLog |
				GatedDiskOut.ar(oBufferLog, 1, [In.ar(aiBusEGG), In.ar(aiBusGateCycle)]);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Write points
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameWritePoints,
			{ | aiBusGate,
				aiBusDeltaAmplitudeFirst,
				aiBusDeltaPhaseFirst,
				oBuffer |

				var gate = In.ar(aiBusGate);
				var damps = In.ar(aiBusDeltaAmplitudeFirst, nHarmonics);
				var dphases = In.ar(aiBusDeltaPhaseFirst, nHarmonics);

				GatedDiskOut.ar(oBuffer, gate, damps ++ dphases);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Write SampEn
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameWriteSampEn,
			{ | aiBusGate,
				aiBusSampEn,
				oBuffer |

				var gate = In.ar(aiBusGate);
				var sampen = In.ar(aiBusSampEn);

				GatedDiskOut.ar(oBuffer, gate, [sampen]);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Write Frequency Amplitude
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameWriteFreqAmp,
			{ | aiBusGate,
				aiBusFrequency,
				aiBusAmplitude,
				oBuffer |

				var gate = In.ar(aiBusGate);
				var freq = In.ar(aiBusFrequency);
				var amp = In.ar(aiBusAmplitude);

				GatedDiskOut.ar(oBuffer, gate, [freq, amp]);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Write Log
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameWriteLog,
			{ | logTimeOffset,
				aiBusGate,
				aiBusTimestamp,
				aiBusFrequency,
				aiBusAmplitude,
				aiBusClarity,
				aiBusCrest,
				aiBusSpecBal,
				ciBusCPPsmoothed,
				aiBusClusterNumber,
				ciBusClusterPhonNumber,
				aiBusSampEn,
				aiBusIcontact,
				aiBusDEGGmax,
				aiBusQcontact,
				aiBusAmplitudeFirst,
				aiBusPhaseFirst,
				oBuffer |

				var freq = In.ar(aiBusFrequency);
				var amp = In.ar(aiBusAmplitude);
				var clarity = In.ar(aiBusClarity);
				var crest = In.ar(aiBusCrest);
				var specBal = In.ar(aiBusSpecBal);
				var cppSmoothed = In.kr(ciBusCPPsmoothed);
				var cluster_number = In.ar(aiBusClusterNumber);
				var phoncluster = In.kr(ciBusClusterPhonNumber);
				var sampen = In.ar(aiBusSampEn);
				var icontact = In.ar(aiBusIcontact);	// vDelayed
				var dEGGmax = In.ar(aiBusDEGGmax);		// vDelayed
				var qContact = In.ar(aiBusQcontact);	// vDelayed
				var amps = In.ar(aiBusAmplitudeFirst, nHarmonics+1);
				var phases = In.ar(aiBusPhaseFirst, nHarmonics+1);
				var gate, time;

				if (logRate > 0, {
					gate = LFPulse.ar(logRate, 0, 0);
					time = In.ar(aiBusTimestamp)  + logTimeOffset;
				}, {
					gate = In.ar(aiBusGate);
					time = In.ar(aiBusGate) + logTimeOffset; // Here, aiBusGate actually holds the delayed timestamp
				});

				// The metric order here must be the same as that returned by *getAllLogMetricNames
				GatedDiskOut.ar(oBuffer, gate,
					[time, freq, amp, clarity, crest, specBal, cppSmoothed, cluster_number, phoncluster, sampen, icontact, dEGGmax, qContact]
					++ amps ++ phases);
			},
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Write Gates
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef(nameWriteGates,
			{ | aiBusEGG,
				aiBusConditionedEGG,
				aiBusGateCycle,
				aiBusGateDelayedCycle,
				aiBusGateFilteredDFT,
				oBuffer |

				var egg = In.ar(aiBusEGG);
				var cegg = In.ar(aiBusConditionedEGG);
				var gcycle = In.ar(aiBusGateCycle);
				var gdcycle = In.ar(aiBusGateDelayedCycle);
				var gfdft = In.ar(aiBusGateFilteredDFT);

				GatedDiskOut.ar(oBuffer, 1, [egg, cegg, gcycle, gdcycle, gfdft]);
			}
		).add(libname);

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Record extra channels if requested
		///////////////////////////////////////////////////////////////////////////////////////////////////////

		if (arrayRecordExtraInputs.notNil , {
			SynthDef(nameRecordExtraChannels,
				{ | oBuffer |
					var physios = SoundIn.ar(arrayRecordExtraInputs);
					var gate = LFPulse.ar(rateExtra, 0, 0);
					GatedDiskOut.ar(oBuffer, gate, physios);
				}
			).add(libname);
		});

	}

/*	*liveInput { | aiBusMic, aiBusEGG, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG ...args |
		^Array.with(nameLiveInput,
			[
				\aiBusMic, aiBusMic,
				\aiBusEGG, aiBusEGG,
				\aoBusMic, aoBusMic,
				\aoBusEGG, aoBusEGG,
				\aoBusConditionedMic, aoBusConditionedMic,
				\aoBusConditionedEGG, aoBusConditionedEGG
			],
			*args
		);
	}
*/
	*liveInput2 { | aiBusMic, aiBusEGG, ciBusNoiseThreshold, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG ...args |
		^Array.with(nameLiveInput2,
			[
				\aiBusMic, aiBusMic,
				\aiBusEGG, aiBusEGG,
				\ciBusNoiseThreshold, ciBusNoiseThreshold,
				\aoBusMic, aoBusMic,
				\aoBusEGG, aoBusEGG,
				\aoBusConditionedMic, aoBusConditionedMic,
				\aoBusConditionedEGG, aoBusConditionedEGG
			],
			*args
		);
	}

	*diskInput { | iBufferDisk, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG ...args |
		^Array.with(nameDiskInput,
			[
				\iBufferDisk, iBufferDisk,
				\aoBusMic, aoBusMic,
				\aoBusEGG, aoBusEGG,
				\aoBusConditionedMic, aoBusConditionedMic,
				\aoBusConditionedEGG, aoBusConditionedEGG
			],
			*args
		);
	}

/*	*diskInput2 { | iBufferDisk, ciBusNoiseThreshold, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG ...args |
		^Array.with(nameDiskInput2,
			[
				\iBufferDisk, iBufferDisk,
				\ciBusNoiseThreshold, ciBusNoiseThreshold,
				\aoBusMic, aoBusMic,
				\aoBusEGG, aoBusEGG,
				\aoBusConditionedMic, aoBusConditionedMic,
				\aoBusConditionedEGG, aoBusConditionedEGG
			],
			*args
		);
	}
*/
	*diskInput3 { | iBufferDisk, ciBusNoiseThreshold, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG ...args |
		^Array.with(nameDiskInput3,
			[
				\iBufferDisk, iBufferDisk,
				\ciBusNoiseThreshold, ciBusNoiseThreshold,
				\aoBusMic, aoBusMic,
				\aoBusEGG, aoBusEGG,
				\aoBusConditionedMic, aoBusConditionedMic,
				\aoBusConditionedEGG, aoBusConditionedEGG
			],
			*args
		);
	}

/*	*diskInput4 { | iBufferDisk, ciBusNoiseThreshold, aoBusMic, aoBusEGG, aoBusConditionedMic, aoBusConditionedEGG, coChainEGGcond ...args |
		^Array.with(nameDiskInput4,
			[
				\iBufferDisk, iBufferDisk,
				\ciBusNoiseThreshold, ciBusNoiseThreshold,
				\aoBusMic, aoBusMic,
				\aoBusEGG, aoBusEGG,
				\aoBusConditionedMic, aoBusConditionedMic,
				\aoBusConditionedEGG, aoBusConditionedEGG,
				\coChainEGGcond, coChainEGGcond
			],
			*args
		);
	}
*/
	*echoMicrophone { | tDelay, aiBusMic, aiBusEGG, aoBusSpeaker ...args |
		^Array.with(nameEchoMicrophone,
			[
				\tDelay, tDelay,
				\aiBusMic, aiBusMic,
				\aiBusEGG, aiBusEGG,
				\aoBusSpeaker, aoBusSpeaker
			],
			*args
		);
	}

	*writeAudio { | aiBusMic, aiBusEGG, oBufferAudio ...args |
		^Array.with(nameWriteAudio,
			[
				\aiBusMic, aiBusMic,
				\aiBusEGG, aiBusEGG,
				\oBufferAudio, oBufferAudio
			],
			*args
		);
	}

	*writeCycleDetectionLog { | aiBusEGG, aiBusGateCycle, oBufferLog ...args |
		^Array.with(nameWriteCycleDetectionLog,
			[
				\aiBusEGG, aiBusEGG,
				\aiBusGateCycle, aiBusGateCycle,
				\oBufferLog, oBufferLog
			],
			*args
		);
	}

	*writePoints { |
		aiBusGate,
		aiBusDeltaAmplitudeFirst,
		aiBusDeltaPhaseFirst,
		oBuffer
		...args |

		^Array.with(nameWritePoints,
			[
				\aiBusGate, aiBusGate,
				\aiBusDeltaAmplitudeFirst, aiBusDeltaAmplitudeFirst,
				\aiBusDeltaPhaseFirst, aiBusDeltaPhaseFirst,
				\oBuffer, oBuffer
			],
			*args
		);
	}

	*writeSampEn { |
		aiBusGate,
		aiBusSampEn,
		oBuffer
		...args |

		^Array.with(nameWriteSampEn,
			[
				\aiBusGate, aiBusGate,
				\aiBusSampEn, aiBusSampEn,
				\oBuffer, oBuffer
			],
			*args
		);
	}

	*writeFrequencyAmplitude { |
		aiBusGate,
		aiBusFrequency,
		aiBusAmplitude,
		oBuffer
		...args |

		^Array.with(nameWriteFreqAmp,
			[
				\aiBusGate, aiBusGate,
				\aiBusFrequency, aiBusFrequency,
				\aiBusAmplitude, aiBusAmplitude,
				\oBuffer, oBuffer
			],
			*args
		);
	}

	*writeLog { |
		logTimeOffset,
		aiBusGate,
		aiBusTimestamp,
		aiBusFrequency,
		aiBusAmplitude,
		aiBusClarity,
		aiBusCrest,
		aiBusSpecBal,
		ciBusCPPsmoothed,
		aiBusClusterNumber,
		ciBusClusterPhonNumber,
		aiBusSampEn,
		aiBusIcontact,
		aiBusDEGGmax,
		aiBusQcontact,
		aiBusAmplitudeFirst,
		aiBusPhaseFirst,
		oBuffer
		...args |

		^Array.with(nameWriteLog,
			[
				\logTimeOffset, logTimeOffset,
				\aiBusGate, aiBusGate,
				\aiBusTimestamp, aiBusTimestamp,
				\aiBusFrequency, aiBusFrequency,
				\aiBusAmplitude, aiBusAmplitude,
				\aiBusClarity, aiBusClarity,
				\aiBusCrest, aiBusCrest,
				\aiBusSpecBal, aiBusSpecBal,
				\ciBusCPPsmoothed, ciBusCPPsmoothed,
				\aiBusClusterNumber, aiBusClusterNumber,
				\ciBusClusterPhonNumber, ciBusClusterPhonNumber,
				\aiBusSampEn, aiBusSampEn,
				\aiBusIcontact, aiBusIcontact,
				\aiBusDEGGmax, aiBusDEGGmax,
				\aiBusQcontact, aiBusQcontact,
				\aiBusAmplitudeFirst, aiBusAmplitudeFirst,
				\aiBusPhaseFirst, aiBusPhaseFirst,
				\oBuffer, oBuffer
			],
			*args
		);
	}

	*writeGates { |
		aiBusEGG,
		aiBusConditionedEGG,
		aiBusGateCycle,
		aiBusGateDelayedCycle,
		aiBusGateFilteredDFT,
		oBuffer
		...args |

		^Array.with(nameWriteGates,
			[
				\aiBusEGG, aiBusEGG,
				\aiBusConditionedEGG, aiBusConditionedEGG,
				\aiBusGateCycle, aiBusGateCycle,
				\aiBusGateDelayedCycle, aiBusGateDelayedCycle,
				\aiBusGateFilteredDFT, aiBusGateFilteredDFT,
				\oBuffer, oBuffer
			],
			*args
		);
	}

	*recordExtraChannels { |
		oBuffer
		...args |

		^Array.with(nameRecordExtraChannels,
			[
				\oBuffer, oBuffer
			],
			*args
		);
	}

}