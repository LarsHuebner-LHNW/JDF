#! /usr/bin/env python2

# -*- coding: utf-8 -*-
"""
Created on Fri Sep 14 11:07:07 2018

@author: Piotr Traczykowski
"""
import tables
import numpy as np
import matplotlib.pyplot as plt
import scipy.ndimage as ndimage
from math import log, floor, ceil, fmod
from scipy import interpolate
import sys
import datetime
import multiprocessing
import time

### The below line os.nice(15) is to reduce the process priority on your system
### This is to allow your system to behave more smoothly while still the
### JDF will utilize all of its resources
import os

os.nice(20)


##################################################################
##################################################################
##################################################################

# Core procedure for JDF routine
def JDF_CORE(f_Z, X_inp, Y_inp, dist_in, smoothing, rand_x, rand_y, DDDz, NoOfElec):
    init_column_dist = np.sum(dist_in, 0)
    Xh = np.linspace(np.min(X_inp), np.max(X_inp), np.rint(smoothing * len(X_inp)))
    Yh = np.linspace(np.min(Y_inp), np.max(Y_inp), np.rint(smoothing * len(Y_inp)))
    f_col_dist = interpolate.interp1d(X_inp, init_column_dist)
    intp_col_dist = f_col_dist(Xh)

    #   Make sure interpolated values are positive
    intp_col_dist = intp_col_dist.clip(min=0.0)
    intp_col_dist = intp_col_dist / np.sum(intp_col_dist)
    x0 = GenerateParticleX(intp_col_dist, rand_x, Xh)

    #   Find corresponding indices and weights in the other dimension
    indx_temp = np.argsort(np.square(x0 - X_inp))

    indx_temp = indx_temp[:2]

    min_val = np.min(indx_temp)
    max_val = np.max(indx_temp)

    X_min = X_inp[min_val]
    X_max = X_inp[max_val]

    tw1 = 1.0 - (x0 - X_min) / (X_max - X_min)
    tw2 = 1.0 - (X_max - x0) / (X_max - X_min)

    init_row_dist = tw1 * dist_in[:, min_val] + tw2 * dist_in[:, max_val]

    #   Pick column distribution type

    f_row_dist = interpolate.interp1d(Y_inp, init_row_dist)
    intp_row_dist = f_row_dist(Yh)

    #   Make sure interpolated values are positive
    intp_row_dist = intp_row_dist.clip(min=0.0)
    intp_row_dist = intp_row_dist / np.sum(intp_row_dist)
    y0 = GenerateParticleY(intp_row_dist, rand_y, Yh)

    return np.vstack((x0, y0, DDDz, NoOfElec))


# Generate particle X coordinate
def GenerateParticleX(PDF_x, ranDx, Xhin):
    Px_CDF = np.cumsum(PDF_x)
    Px_CDF = np.sort(Px_CDF)
    f_X = interpolate.interp1d(Px_CDF, Xhin, fill_value="extrapolate")
    x0 = f_X(ranDx)
    return x0


# Generate particle Y coordinate
def GenerateParticleY(PDF_y, ranDy, Yhin):
    Py_CDF = np.cumsum(PDF_y)
    Py_CDF = np.sort(Py_CDF)
    f_Y = interpolate.interp1d(Py_CDF, Yhin, fill_value="extrapolate")
    y0 = f_Y(ranDy)
    return y0


# Generate Halton sequences
def HaltonRandomNumber(dims, nb_pts):
    hArr = np.empty(nb_pts * dims)
    hArr.fill(np.nan)
    pArr = np.empty(nb_pts)
    pArr.fill(np.nan)
    Primes = [
        2,
        3,
        5,
        7,
        11,
        13,
        17,
        19,
        23,
        29,
        31,
        37,
        41,
        43,
        47,
        53,
        59,
        61,
        67,
        71,
        73,
        79,
        83,
        89,
        97,
        101,
        103,
        107,
        109,
        113,
        127,
        131,
        137,
        139,
        149,
        151,
        157,
        163,
    ]
    log_nb_pts = log(nb_pts + 1)
    for i in range(dims):
        b = Primes[i]
        n = np.int(np.ceil(log_nb_pts / np.log(b)))
        for t in range(n):
            pArr[t] = np.float_power(b, -(t + 1))

        for j in range(nb_pts):
            d = j + 1
            sum_ = np.fmod(d, b) * pArr[0]
            for t in range(1, n):
                d = np.floor(d / b)
                sum_ += np.fmod(d, b) * pArr[t]
            hArr[j * dims + i] = sum_
    return hArr.reshape(nb_pts, dims)


# Routine that calculates new microparticles positions and weights for selected (just one) slice
def SliceCalculate(
    bin_x_in,
    bin_y_in,
    z_hlt,
    i,
    StepZ,
    NumberOfSlices,
    interpolator,
    f_Z,
    new_x,
    new_y,
    Non_Zero_Z,
    Num_Of_Slice_Particles,
    minz,
    JDFSmoothing,
    RandomHaltonSequence,
):
    print "Slice ", i, " of ", NumberOfSlices
    new_z = np.full((1), (minz + (StepZ * i)))
    xx, yy, zz = np.meshgrid(new_x, new_y, new_z)
    positionsin = np.column_stack(
        (
            xx.ravel("F"),
            yy.ravel("F"),
            zz.ravel("F"),
            interpolator(xx, yy, zz).ravel("F"),
        )
    )
    xy_flat = np.vstack((positionsin[:, 0], positionsin[:, 1])).T
    hist2d_flat, edges = np.histogramdd(
        xy_flat, bins=(bin_x_in, bin_y_in), weights=positionsin[:, 3]
    )
    # if np.sum(hist2d_flat)>0:
    Dist = hist2d_flat
    Xin = np.linspace(np.min(positionsin[:, 0]), np.max(positionsin[:, 0]), bin_x_in)
    Yin = np.linspace(np.min(positionsin[:, 1]), np.max(positionsin[:, 1]), bin_y_in)
    dots = []
    ZZZ = minz + (i * StepZ)
    ZZZ_in = np.full((Num_Of_Slice_Particles), minz + (i * StepZ) + (StepZ * z_hlt))
    NoOfElec = (Non_Zero_Z) * (f_Z(ZZZ) / (NumberOfSlices)) / (Num_Of_Slice_Particles)
    for j in range(0, Num_Of_Slice_Particles):
        result = JDF_CORE(
            f_Z,
            Xin,
            Yin,
            Dist,
            JDFSmoothing,
            RandomHaltonSequence[j, 0],
            RandomHaltonSequence[j, 1],
            ZZZ_in[j],
            NoOfElec,
        )
        dots.append(result[:, 0])
    return dots


##################################################################
##################################################################
##################################################################


# Main routine for JDF
if __name__ == "__main__":

    if len(sys.argv) == 2:
        file_name_in = sys.argv[1]
        print "Processing file:", file_name_in
    else:
        print "Usage: JDF_NLIST <Input File Name>\n"
        sys.exit(1)
    file_name_base = file_name_base = (".".join(file_name_in.split(".")[:-1])).strip()

    import PARAMS_JDF

    #  Set default parameters and read from parameters file

    try:
        k_u = PARAMS_JDF.k_u
    except (NameError, AttributeError) as e:
        k_u = 228.4727
    try:
        a_u = PARAMS_JDF.a_u
    except (NameError, AttributeError) as e:
        a_u = 1.0121809
    try:
        SlicesMultiplyFactor = PARAMS_JDF.SlicesMultiplyFactor
    except (NameError, AttributeError) as e:
        SlicesMultiplyFactor = 10
    try:
        Num_Of_Slice_Particles = PARAMS_JDF.NumOfSliceParticles
    except (NameError, AttributeError) as e:
        Num_Of_Slice_Particles = 800
    try:
        binnumber_X = PARAMS_JDF.X_DensitySampling
    except (NameError, AttributeError) as e:
        binnumber_X = 40
    try:
        binnumber_Y = PARAMS_JDF.Y_DensitySampling
    except (NameError, AttributeError) as e:
        binnumber_Y = 40
    try:
        binnumber_Z = PARAMS_JDF.Z_DensitySampling
    except (NameError, AttributeError) as e:
        binnumber_Z = 40
    try:
        S_factor = PARAMS_JDF.BeamStretchFactor
    except (NameError, AttributeError) as e:
        S_factor = 0.0
    try:
        RNG_seed = PARAMS_JDF.RNG_seed
    except (NameError, AttributeError) as e:
        RNG_seed = np.random.randint(0, 2 ** 32)
    try:
        out_file = str(PARAMS_JDF.out_file)
    except (NameError, AttributeError) as e:
        # default name = base name + JDF + seed
        out_file = file_name_base + "_JDF_" + str(RNG_seed) + ".h5"

    print ("random number generator seed is initialized to", RNG_seed)
    np.random.seed(RNG_seed)
    # Print to screen parameters used for calculations.
    # ==============================================================================
    print "User defined parameters:"
    print "k_u = ", k_u
    print "a_u = ", a_u
    print "Slices per wavelnegth = ", SlicesMultiplyFactor
    # print 'Particle density samples = ',binnumber
    print "Density sampling in X = ", binnumber_X
    print "Density sampling in Y = ", binnumber_Y
    print "Current / Density sampling in Z =", binnumber_Z
    print "Stretching factor in Z = ", S_factor
    # print 'Shape sampling number = ',NumShapeSlices
    # ==============================================================================

    f = tables.open_file(file_name_in, "r")
    Particles = f.root.Particles.read()

    # Filter the particles with z values

    # *************************************************************
    # The below section calculates size of the bin according
    # to value of Lc (binnumbers=total_length/Lc)
    # USER DATA - MODIFY ACCORDING TO REQUIREMENTS
    Pi = np.pi  # Pi number taken from 'numpy' as more precise than just 3.1415
    c = 299792458.0  # Speed of light
    m = 9.11e-31  # mass of electron
    e_0 = 8.854e-12  # vacuum permitivity
    e_ch = 1.602e-19  # charge of one electron

    # *************************************************************
    JDFSmoothing = 1.0

    # Select slice from the beam
    # print len(Particles)
    # midZ=np.mean(Particles[:,4])
    # zlen=0.20*(np.max(Particles[:,4])-np.min(Particles[:,4]))
    # Particles=Particles[(Particles[:,4] < (midZ+zlen)) & (Particles[:,4] > (midZ-zlen))]
    # print len(Particles)

    mA_X = Particles[:, 0]
    mA_Y = Particles[:, 2]
    mA_Z = Particles[:, 4]
    # Descale the momentum units from p/mc to SI - to keep compatibility with rest of calculations
    mA_PX = Particles[:, 1] * (m * c)
    mA_PY = Particles[:, 3] * (m * c)
    mA_PZ = Particles[:, 5] * (m * c)
    mA_WGHT = Particles[:, 6]

    # The below section calculate some initial data - 4*Pi*Rho is the one mose desired
    xyz = np.vstack([mA_X, mA_Y, mA_Z]).T
    size_x = max(mA_X) - min(mA_X)
    size_y = max(mA_Y) - min(mA_Y)
    size_z = max(mA_Z) - min(mA_Z)
    minx = np.min(mA_X)
    maxx = np.max(mA_X)
    miny = np.min(mA_Y)
    maxy = np.max(mA_Y)
    print "Size of sample X,Y,Z = ", size_x, size_y, size_z

    # Calculate some needed values: Omega,Rho,Lc,Lambda_U,Lambda_R,
    p_tot = np.sqrt((mA_PX[:] ** 2) + (mA_PY[:] ** 2.0) + (mA_PZ[:] ** 2.0))
    gamma = np.sqrt(1 + (p_tot / (m * c)) ** 2.0)
    gamma_0 = np.mean(gamma)
    RandomHaltonSequence = HaltonRandomNumber(2, Num_Of_Slice_Particles)
    z_hlt = 0.5 - HaltonRandomNumber(2, Num_Of_Slice_Particles)
    # RandomHaltonSequence=np.random.rand(Num_Of_Slice_Particles,2)
    ## Linear smoothing between bins in JDF_CORE

    lambda_u = (2.0 * Pi) / k_u
    # Use plane-pole undulator
    lambda_r = (lambda_u / (2.0 * gamma_0 ** 2.0)) * (1 + (a_u ** 2.0) / 2.0)
    print "Using plane-pole undulator configuration !"

    # Use helical undulator
    # lambda_r=(lambda_u/(2*gamma_0**2))*(1+a_u**2)
    # print 'Using helical undulator configuration !'
    print "lambda_r = ", lambda_r

    NumberOfSlices = int(
        SlicesMultiplyFactor
        * ((max(mA_Z) + S_factor * size_z) - (min(mA_Z) - S_factor * size_z))
        / (lambda_r)
    )
    TotalNumberOfElectrons = np.sum(mA_WGHT)
    InitialParticleCharge = TotalNumberOfElectrons * e_ch

    Hz, edges_Z = np.histogram(
        mA_Z,
        bins=binnumber_Z,
        normed=False,
        weights=mA_WGHT,
        range=((min(mA_Z) - S_factor * size_z, max(mA_Z) + S_factor * size_z)),
    )
    Hz = ndimage.gaussian_filter(Hz, 1.0)
    Non_Zero_Z = float(np.count_nonzero(Hz))
    # x0_Z = np.linspace(0.5*(edges_Z[0][0]+edges_Z[0][1]),0.5*(edges_Z[0][binnumber_Z]+edges_Z[0][binnumber_Z-1]),binnumber_Z)
    x0_Z = np.linspace(
        0.5 * (edges_Z[0] + edges_Z[1]),
        0.5 * (edges_Z[binnumber_Z] + edges_Z[binnumber_Z - 1]),
        binnumber_Z,
    )
    y0_Z = Hz

    f_Z = interpolate.PchipInterpolator(x0_Z, y0_Z)
    m_Z_plt = np.linspace(
        min(mA_Z) - S_factor * size_z, max(mA_Z) + S_factor * size_z, 100
    )
    plt.plot(m_Z_plt, f_Z(m_Z_plt))
    plt.show()

    start = time.time()
    x0y0z0 = np.vstack((mA_X, mA_Y, mA_Z)).T

    # Create 3D particles density map
    HxHyHz, edges_XYZ = np.histogramdd(
        x0y0z0, bins=(binnumber_X, binnumber_Y, binnumber_Z), weights=mA_WGHT
    )
    print "Histogram done..."
    # Apply Gaussian filter to smoothen density map artifacts (1.0 is default value)
    # if user wish to use 'raw' data the below line should be commented
    HxHyHz = ndimage.gaussian_filter(HxHyHz, 1.0)

    # Map the 3D density map onto equispaced meshgrid
    new_x = np.linspace(np.min(mA_X), np.max(mA_X), binnumber_X)
    new_y = np.linspace(np.min(mA_Y), np.max(mA_Y), binnumber_Y)
    new_z = np.linspace(np.min(mA_Z), np.max(mA_Z), binnumber_Z)

    xxh, yyh, zzh = np.meshgrid(new_x, new_y, new_z)
    positions = np.column_stack(
        (xxh.ravel("F"), yyh.ravel("F"), zzh.ravel("F"), HxHyHz.ravel("F"))
    )
    ## The below line removes or histogram values < 0 what improves performance
    positions = positions[positions[:, 3] > 0.0]
    xyzpoints = np.vstack((positions[:, 0], positions[:, 1], positions[:, 2])).T

    # Interpolate the 3D histogram (meshgrid) into continuous distribution (nearest neighbor or linear interpolation allowed)
    ### Linear interpolation - slow but more accurate
    # interpolator=interpolate.LinearNDInterpolator(xyzpoints,positions[:,3],rescale=True,fill_value=0)

    ### Nearest neighbour interpolation - fast and less accurate

    interpolator = interpolate.NearestNDInterpolator(
        xyzpoints, positions[:, 3], rescale=True
    )

    ### Below is option to plot the density map of the beam - uncomment if you want to see one.
    # ==============================================================================
    # from mpl_toolkits.mplot3d import Axes3D
    # fig = plt.figure()
    # ax = fig.add_subplot(111, projection='3d')
    # ax.scatter(xyzpoints[:,0],xyzpoints[:,1],xyzpoints[:,2],c=positions[:,3])
    # plt.show()
    # ==============================================================================

    print "Interpolation map created..."

    minz = np.min(x0y0z0[:, 2])
    maxz = np.max(x0y0z0[:, 2])

    StepZ = (maxz - minz) / NumberOfSlices

    # Sweep over all slices along Z-axis (longitudinal direction) and generate new microparticles
    # Routine is parallel and uses ALL available cores
    pool = multiprocessing.Pool()
    print "Executing main JDF loop..."
    result2 = []
    # Create list of slices to calculate - with positive value of current, avoids further checks in algorithm.
    slice_list = []
    # parallel routine
    for slice_number in range(0, NumberOfSlices):
        ZZZ = minz + (slice_number * StepZ)
        NoOfElec = (
            (Non_Zero_Z) * (f_Z(ZZZ) / (NumberOfSlices)) / (Num_Of_Slice_Particles)
        )
        if NoOfElec > 0:
            slice_list.append(slice_number)

    for slice_number in slice_list:
        pool.apply_async(
            SliceCalculate,
            args=(
                binnumber_X,
                binnumber_Y,
                z_hlt[:, 1],
                slice_number,
                StepZ,
                NumberOfSlices,
                interpolator,
                f_Z,
                new_x,
                new_y,
                Non_Zero_Z,
                Num_Of_Slice_Particles,
                minz,
                JDFSmoothing,
                RandomHaltonSequence,
            ),
            callback=result2.append,
        )
    pool.close()
    pool.join()

    # ==============================================================================
    # ## SERIAL VERSION DEBUG ONLY !!!
    #    for slice_number in range(0,NumberOfSlices):
    #        ZZZ=minz+(slice_number*StepZ)
    #        NoOfElec=(Non_Zero_Z)*(f_Z(ZZZ)/(NumberOfSlices))/(Num_Of_Slice_Particles)
    #        if NoOfElec>0:
    #            results=SliceCalculate(binnumber_X,binnumber_Y,z_hlt[:,1],slice_number,StepZ,NumberOfSlices,interpolator,f_Z,new_x,new_y,Non_Zero_Z,Num_Of_Slice_Particles,minz,JDFSmoothing,RandomHaltonSequence)
    #            result2.append(results)
    # ==============================================================================

    # Rearrange the output from parallel loop above
    print "Output array shape is: ", np.shape(result2)
    Total_Number_Of_Particles = len(result2) * Num_Of_Slice_Particles
    print "Total number of particles = ", Total_Number_Of_Particles
    Full_X = np.zeros(Total_Number_Of_Particles)
    Full_PX = np.zeros(0)
    Full_Y = np.zeros(Total_Number_Of_Particles)
    Full_PY = np.zeros(0)
    Full_Z = np.zeros(Total_Number_Of_Particles)
    Full_PZ = np.zeros(0)
    Full_Ne = np.zeros(Total_Number_Of_Particles)
    print "Starting rearranging array..."
    counter = 0
    for j in range(0, Num_Of_Slice_Particles):
        for i in range(0, len(result2)):
            Full_X[counter] = result2[i][j][0]
            Full_Y[counter] = result2[i][j][1]
            Full_Z[counter] = result2[i][j][2]
            Full_Ne[counter] = result2[i][j][3]
            counter = counter + 1
    # Generate noise
    # Add noise
    print "Adding noise..."
    Rand_Z = (StepZ * (np.random.random(len(Full_Z)) - 0.50)) / np.sqrt(Full_Ne)
    Full_Z = Full_Z + Rand_Z
    # Interpolate momentum data onto new microparticles (griddata used)
    print "Starting to interpolate momentum data... - takes time"

    def Calculate_PX():
        Full_PX = interpolate.griddata(
            (mA_X.ravel(), mA_Y.ravel(), mA_Z.ravel()),
            mA_PX.ravel(),
            (Full_X, Full_Y, Full_Z),
            method="linear",
            rescale=True,
        )
        return Full_PX

    def Calculate_PY():
        Full_PY = interpolate.griddata(
            (mA_X.ravel(), mA_Y.ravel(), mA_Z.ravel()),
            mA_PY.ravel(),
            (Full_X, Full_Y, Full_Z),
            method="linear",
            rescale=True,
        )
        return Full_PY

    def Calculate_PZ():
        Full_PZ = interpolate.griddata(
            (mA_X.ravel(), mA_Y.ravel(), mA_Z.ravel()),
            mA_PZ.ravel(),
            (Full_X, Full_Y, Full_Z),
            method="linear",
            rescale=True,
        )
        return Full_PZ

    # Parallel momentum data mapping
    from multiprocessing.pool import ThreadPool

    pool = ThreadPool(processes=3)
    async_result_PX = pool.apply_async(Calculate_PX, ())
    async_result_PY = pool.apply_async(Calculate_PY, ())
    async_result_PZ = pool.apply_async(Calculate_PZ, ())
    Full_PX = async_result_PX.get()
    Full_PY = async_result_PY.get()
    Full_PZ = async_result_PZ.get()

    # Scale units from SI to p = p/mc

    Full_PX = Full_PX / (m * c)
    Full_PY = Full_PY / (m * c)
    Full_PZ = Full_PZ / (m * c)

    # Merge all data into one array
    x_px_y_py_z_pz_NE = np.vstack(
        [
            Full_X.flat,
            Full_PX.flat,
            Full_Y.flat,
            Full_PY.flat,
            Full_Z.flat,
            Full_PZ.flat,
            Full_Ne.flat,
        ]
    ).T

    # Add Poisson noise to particle weights
    x_px_y_py_z_pz_NE[:, 6] = np.random.poisson(x_px_y_py_z_pz_NE[:, 6])

    # Remove all particles with weights <= zero
    x_px_y_py_z_pz_NE = x_px_y_py_z_pz_NE[x_px_y_py_z_pz_NE[:, 6] > 0]

    # Check for NaN calues in data - it sometimes happen when using 'linear' option in momentum interpolations (griddata parameter)
    NaN_Mask = ~np.any(np.isnan(x_px_y_py_z_pz_NE), axis=1)
    x_px_y_py_z_pz_NE = x_px_y_py_z_pz_NE[NaN_Mask]

    # Rescale the charge of new particle set (needed due to S_factor usage)
    ChargeFactor = InitialParticleCharge / np.sum(x_px_y_py_z_pz_NE[:, 6] * e_ch)
    print "Charge scaling factor = ", ChargeFactor
    x_px_y_py_z_pz_NE[:, 6] = x_px_y_py_z_pz_NE[:, 6] * ChargeFactor

    print "Final charge of particles = ", np.sum(x_px_y_py_z_pz_NE[:, 6] * e_ch)
    print "Saving the output to files..."

    # Create Group in HDF5 and add metadata for Visit
    # Open output file
    output_file = tables.open_file(out_file, "w")
    ParticleGroup = output_file.create_array("/", "Particles", x_px_y_py_z_pz_NE)
    boundsGroup = output_file.create_group("/", "globalGridGlobalLimits", "")
    boundsGroup._v_attrs.vsType = "limits"
    boundsGroup._v_attrs.vsKind = "Cartesian"
    timeGroup = output_file.create_group("/", "time", "time")
    timeGroup._v_attrs.vsType = "time"
    ParticleGroup._v_attrs.vsType = "variableWithMesh"
    ParticleGroup._v_attrs.vsTimeGroup = "time"
    ParticleGroup._v_attrs.vsNumSpatialDims = 3
    ParticleGroup._v_attrs.vsLimits = "globalGridGlobalLimits"
    ParticleGroup._v_attrs.vsLabels = "x,px,y,py,z,pz,NE"
    now = datetime.datetime.now()
    ParticleGroup._v_attrs.FXFELConversionTime = now.strftime("%Y-%m-%d %H:%M:%S")
    ParticleGroup._v_attrs.FXFELSourceFileName = file_name_in
    # Close the file
    output_file.close()
    end = time.time()
    print "Time of work: ", end - start
