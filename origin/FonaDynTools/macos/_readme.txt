The first time you run FonaDyn on a Mac, the computer must be connected to the Internet, or Apple's safety checks will not work. 

These .scx files are built to support SuperCollider 3.14.x universal binary, i.e., with either ARM and Intel hardware. They should also run on legacy Intel Macs. 

This build of the MacOS UGens for FonaDyn presumes that SuperCollider is installed in the default location. The UGens GatedDiskOut.scx and PitchDetection.scx will want to link directly to dylibs in that location. The FonaDyn.install routine selects either "universal" or "legacy-x64", as appropriate, for these two plugins (the .dylibs have different names depending on the SC version).

On FonaDyn.install, the library PitchDetection.scx in this folder replaces the one in sc3-plugins. The version here is linked with the FFTW3 libraries instead of with the Apple vDSP libraries, which do not give exactly the same result. 
Running FonaDyn.uninstall will reinstate the original PitchDetection.scx. 

