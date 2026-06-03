import os
import math
import numpy as np

def generate_cylinder_vertex(Re, Radius=1.0):
    """Generate vertex file for a cylinder with given Reynolds number"""
    # Create output directory if it doesn't exist
    output_dir = "vertex_files"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Parameters
    D = 2 * Radius
    Lx = 20.0 * D
    Ly = 20.0 * D
    
    # Calculate grid size based on Reynolds number
    Nx = 800 + 2*math.ceil(Re/10)
    Ny = 800 + 2*math.ceil(Re/10)
    
    # Calculate grid spacing
    dx = Lx / Nx
    dy = Ly / Ny
    
    # Cylinder parameters
    X_com = 0.0
    Y_com = 0.0
    
    # Calculate number of points
    num_pts_x = math.ceil(2 * Radius / dx)
    num_pts_y = math.ceil(2 * Radius / dy)
    
    # Generate points
    X_array = []
    Y_array = []
    
    for i in range(1, num_pts_x + 1):
        x = X_com + ((i-1) * dx - Radius)
        
        for j in range(1, num_pts_y + 1):
            y = Y_com + ((j-1) * dy - Radius)
            
            if ((x - X_com)**2 + (y - Y_com)**2) <= Radius**2:
                X_array.append(x)
                Y_array.append(y)
    
    # Calculate center of mass
    XCOM = sum(X_array) / len(X_array)
    YCOM = sum(Y_array) / len(Y_array)
    
    # Adjust points relative to center of mass
    X_array = [x - XCOM for x in X_array]
    Y_array = [y - YCOM for y in Y_array]
    
    # Write the coordinates to file
    vertex_file = os.path.join(output_dir, f"cylinder2d_Re{Re}.vertex")
    with open(vertex_file, 'w') as f:
        f.write(f"{len(X_array)}\n")
        for i in range(len(X_array)):
            f.write(f"{X_array[i]}\t{Y_array[i]}\n")
    
    print(f"Generated vertex file for Re = {Re} with {len(X_array)} points")
    return vertex_file

def main():
    # Reynolds numbers to generate
    reynolds_numbers = range(500, 2501, 500)
    
    print("Generating vertex files for different Reynolds numbers...")
    
    for Re in reynolds_numbers:
        vertex_file = generate_cylinder_vertex(Re)
        print(f"  File created: {vertex_file}")
        print()
    
    print("All vertex files generated successfully!")

if __name__ == "__main__":
    main()

