# -*- coding: utf-8 -*-
"""
Created on Sat Mar 23 14:06:56 2019

@author: StefM
"""

PrintLevel   = 5
Emissiviteit = 0.95
Lamel_Eff    = 1.3
Print_Checks = True

#https://www.engineeringtoolbox.com/air-absolute-kinematic-viscosity-d_601.html

# in free convection, 
# plays the same role as the Reynolds number in forced convection
# for vertical plates, turbulent flow if Grashof > 10**9
# Controle: https://www.thermal-wizard.com/tmwiz/default.htm
# 
# https://en.wikipedia.org/wiki/Grashof_number
 

Bolzman      = 0.0000000567 



# ***************************************************************************
# Bereken de capaciteit bij een andere temperatuur
# ***************************************************************************
def Capacity_dT ( dT1, P1, dT2, n=1.33 ) :
  P2 = P1 * ( ( dT2 / dT1 ) ** n )  
  return int ( P2 )


# ***************************************************************************
  # Bereken de capaciteit
# ***************************************************************************
def Rad_Conv ( Th, Tl, Hoogte, Breedte, N_Panel, N_Lamel, AirSpeed=0 ) :

  # ************************************
  # Oppervlakte van 1 zijde van 1 paneel
  # ************************************
  Opp = Hoogte * Breedte

  # ************************************
  # Straling is enkel van belang voor de 2 buitenste vlakken
  # ************************************
  Radiation  = int ( Emissiviteit * Bolzman * ( (273+Th)**4 - (273+Tl)**4 ) * 2 * Opp )

  # ************************************
  # Bereken de convectie voor de buiten oppervlakten
  # ************************************
  Delta_T = Th - Tl
  X = Heat_Transfer ()
  X.Convection_h ( Delta_T, Hoogte )
  h_WOC = X.WOC
  Convection = int ( h_WOC * ( Th - Tl ) * 2 * Opp )

  # ************************************
  # Bereken de convectie voor de binnen oppervlakten
  # al dan niet met forced airflow
  # ************************************
  Delta_T = Th - Tl
  X = Heat_Transfer ()
  X.Convection_h ( Delta_T, Hoogte, AirSpeed )
  h_WOC_Forced = X.WOC
  Convection += int ( h_WOC_Forced * ( Th - Tl ) * ( N_Panel - 1 + Lamel_Eff * N_Lamel ) * 2 * Opp )

  Total = Radiation + Convection
  return Radiation, Convection, Total



# ***************************************************************************
# ***************************************************************************
class Heat_Transfer ( object ) :
  # *********************************************
  def __init__ ( self ) :
    self.Specific_Heat        = 1007       # [J/kg.K]
    self.Thermal_Conductivity = 0.0261     # [W/m.K]
    self.Gravity              = 9.81       # [m/s2]
    self.Thermal_Expansion    = 1/300      # [1/K] equal to approximately 1/T
  
  # *********************************************
  # Berekent de warmte overdrachts coefficient h
  # voor zowel free als forced air flow
  # *********************************************
  def Convection_h ( self, Delta_T, Hoogte, Forced_Speed = 0 ) :
    self.Delta_T      = Delta_T
    self.Hoogte       = Hoogte
    self.Forced_Speed = Forced_Speed

    # **************************************  
    # Viscositeit is temperatuur afhankelijk,
    # in dit geval gebruiken we de Sutherland formule, maar er zijn meer benaderingen
    # hier nemen we de gemiddelde radiator temperatuur,
    #   niet helemaal duidelijk of dat de meest geschikte waarde
    #   als we film temperatuur nemen, maakt niet veel uit
    # **************************************
    b = 1.458e-6
    S = 110.4
    T = 273 + 20 + Delta_T
    self.Viscosity_Dynamic = b * ( T ** ( 3/2 )) / ( T + S )
    
    # ************************************
    # Dichtheid is temperatuur afhankelijk
    # hier is het duidelijk datwe filmtemperatuur
    #    temperatuur halverwege plaat / lucht moeten nemen
    # ************************************
    T = 273 + 20 + Delta_T / 2
    self.Density = 358.517 * ( T ** -1.00212 )
   
    self.Prandtl = self.Viscosity_Dynamic * self.Specific_Heat / self.Thermal_Conductivity
    
    self.Grashof = int ( self.Gravity * \
                         self.Thermal_Expansion * \
                         self.Delta_T * \
                         ( self.Hoogte ** 3 ) * \
                         ( self.Density ** 2 ) \
                         / \
                         ( self.Viscosity_Dynamic ** 2 ) )
    self.Rayleigh = int ( self.Grashof * self.Prandtl )

    if self.Rayleigh < 1e9 :
      self.Nusselt = 0.68 + 0.67 * ( self.Rayleigh ** (1/4) ) / \
                                   (( 1 + ( 0.492 / self.Prandtl ) ** ( 9/16 )) ** (4/9))
    else :
      self.Nusselt = ( 0.825 + 0.387 * ( self.Rayleigh ** (1/6) ) / \
                       (( 1 + ( 0.492 / self.Prandtl ) ** (9/16) ) ** ( 8/27 )) \
                     ) ** 2

    self.h_WOC = self.Nusselt * self.Thermal_Conductivity / self.Hoogte
    self.Use_Reynolds     = False
    self.Reynolds         = 0
    self.Grashof_Reynolds = 0
    self.h_WOC_Forced     = 0
    #self.Nusselt_Total    = 0
    #self.h_WOC_Total      = 0
    self.WOC              = self.h_WOC
    
    if self.Forced_Speed > 0 :
      self.Reynolds = self.Forced_Speed * self.Hoogte * self.Density / self.Viscosity_Dynamic
      self.Nusselt_Forced = 0.664 * ( self.Reynolds ** 0.5 ) * ( self.Prandtl ** 0.33 )
      self.h_WOC_Forced = self.Nusselt_Forced * self.Thermal_Conductivity / self.Hoogte
      self.Grashof_Reynolds = self.Grashof / ( self.Reynolds ** 2 )

      self.Nusselt = ( ( self.Nusselt ** 3 ) + ( self.Nusselt_Forced ** 3 ) ) ** (1/3)
      self.WOC = self.Nusselt * self.Thermal_Conductivity / self.Hoogte
      
      # *************************************************
      # we hebben op zijn minst de natuurlijke convectie,
      # dus forced airflow moet een grotere invvloed hebben om actief te worden
      # *************************************************
      #if self.h_WOC_Forced > self.h_WOC :
      #  self.Use_Reynolds = True
      #  self.WOC = self.h_WOC_Forced

  # *********************************************
  def __repr__ ( self ) :
    Line = "=====  Convection:   Delta_T = %i [K]    Hoogte = %.1f [m]    Forced_Speed = %.1f [m/s]\n" % (
            self.Delta_T, self.Hoogte, self.Forced_Speed ) 
    Line += "Prandtl  (=0.714)  : %.3f\n" % ( self.Prandtl )
    Line += "Grashof  (=9.02e8) : %.2e\n" % ( self.Grashof )
    if self.Use_Reynolds :
      #Line += "Reynolds Turbulent : >5.00e+09  <=====\n"
      Line += "Reynolds (=6.44e8) : %.2e\n" % ( self.Reynolds )
      Line += "Nusselt  (=82.6  ) : %.1f\n" % ( self.Nusselt_Forced )
    else :
      Line += "Rayleigh Turbulent : >5.00e+09  <=====\n"
      Line += "Rayleigh (=6.44e8) : %.2e\n" % ( self.Rayleigh )
      Line += "Nusselt  (=82.6  ) : %.1f\n" % ( self.Nusselt )
    if self.Grashof_Reynolds != 0 :
      Line += "Gr / Re^2          : %.2f\n" % ( self.Grashof_Reynolds )
    Line += "h        (=3.08  ) : %.2f [W/m2.K]\n" % ( self.WOC )
    return Line


# ***************************************************************************    
# ***************************************************************************    
class Radiator_Class ( object ) :
  # ***********************************************
  def __init__ ( self, Name, Breedte, Hoogte, Type, Ptot=-1, Delta_T=-1, URL="", Px=35 ) :
    self.Name        = Name
    self.Breedte     = Breedte / 1000
    self.Hoogte      = Hoogte / 1000
    self.Type        = Type
    self.URL         = URL
    self.Opp         = self.Breedte * self.Hoogte
    self.N_Panel     = Type // 10
    self.N_Lamel     = Type % 10
    self.Vent_Aantal = 0
    self.Px          = Px

    self.P20       = -1
    self.P35       = -1
    self.P50       = -1
    self.P60       = -1
    
    self.P20_Rad_VV  = -1
    self.P20_Conv_VV = -1
    self.P20_Tot_VV  = -1
    self.P35_Rad_VV  = -1
    self.P35_Conv_VV = -1
    self.P35_Tot_VV  = -1
    self.P50_Rad_VV  = -1
    self.P50_Conv_VV = -1
    self.P50_Tot_VV  = -1
    self.P60_Rad_VV  = -1
    self.P60_Conv_VV = -1
    self.P60_Tot_VV  = -1


    if ( Ptot > 0 ) and ( Delta_T > 0 ) :    
      if Delta_T == 20 :
        self.P20 = Ptot
        self.P50 = Capacity_dT ( 20, Ptot, 50 )
        self.P60 = Capacity_dT ( 20, Ptot, 60 )
      elif Delta_T == 50 :
        self.P20 = Capacity_dT ( 50, Ptot, 20 )
        self.P50 = Ptot
        self.P60 = Capacity_dT ( 50, Ptot, 60 )
      elif Delta_T == 60 :
        self.P20 = Capacity_dT ( 60, Ptot, 20 )
        self.P50 = Capacity_dT ( 60, Ptot, 50 )
        self.P60 = Ptot
      else :
        self.P20 = Capacity_dT ( Delta_T, Ptot, 20 )
        self.P50 = Capacity_dT ( Delta_T, Ptot, 50 )
        self.P60 = Capacity_dT ( Delta_T, Ptot, 60 )
        
    self.Capaciteit ()
  
  # ***********************************************
  def Capaciteit ( self ) :
    self.P20_Radiation, self.P20_Convection, self.P20_Tot = \
      Rad_Conv ( Th=40, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel) 
    self.P35_Radiation, self.P35_Convection, self.P35_Tot = \
      Rad_Conv ( Th=20+self.Px, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel) 
    self.P50_Radiation, self.P50_Convection, self.P50_Tot = \
      Rad_Conv ( Th=70, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel) 
    self.P60_Radiation, self.P60_Convection, self.P60_Tot = \
      Rad_Conv ( Th=80, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel) 
    
    # **************************************************
    # en bereken ook een paar waarden met forced airflow
    # **************************************************
    self.P20_Rad_V1, self.P20_Conv_V1, self.P20_Tot_V1 = \
      Rad_Conv ( Th=40, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel, AirSpeed=1 ) 
    self.P20_Rad_V2, self.P20_Conv_V2, self.P20_Tot_V2 = \
      Rad_Conv ( Th=40, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel, AirSpeed=2 ) 
    self.P20_Rad_V3, self.P20_Conv_V3, self.P20_Tot_V3 = \
      Rad_Conv ( Th=40, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel, AirSpeed=3 ) 
    
    self.P20_perc_Radiation  = round ( 100 * self.P20_Radiation  / self.P20_Tot )
    self.P35_perc_Radiation  = round ( 100 * self.P35_Radiation  / self.P35_Tot )
    self.P50_perc_Radiation  = round ( 100 * self.P50_Radiation  / self.P50_Tot )
    self.P60_perc_Radiation  = round ( 100 * self.P60_Radiation  / self.P60_Tot )

    self.P20_perc_Convection = round ( 100 * self.P20_Convection / self.P20_Tot )
    self.P35_perc_Convection = round ( 100 * self.P35_Convection / self.P35_Tot )
    self.P50_perc_Convection = round ( 100 * self.P50_Convection / self.P50_Tot )
    self.P60_perc_Convection = round ( 100 * self.P60_Convection / self.P60_Tot )
    
    if self.P20 == -1 : self.P20 = self.P20_Tot
    if self.P35 == -1 : self.P35 = self.P35_Tot
    if self.P50 == -1 : self.P50 = self.P50_Tot
    if self.P60 == -1 : self.P60 = self.P60_Tot

  # ***********************************************
  def Add_Ventilator ( self, Aantal=1, Diameter=12, Flow=100 ) :
    self.Vent_Flow     = Flow              # [m3/hr]
    self.Vent_Diameter = Diameter / 100    # [cm]  ==> [m]
    self.Vent_Aantal   = Aantal
    Opp_Tot = self.Vent_Diameter * self.Breedte
    self.Vent_AirSpeed = self.Vent_Aantal * self.Vent_Flow / ( Opp_Tot* 3600 )
    print ( "Ventilator, N=%i, Flow=%i[m3/hr],  Forced AirSpeed = %.1f [m/s]" % ( 
            self.Vent_Aantal, self.Vent_Flow, self.Vent_AirSpeed ) )

    self.P20_Rad_VV, self.P20_Conv_VV, self.P20_Tot_VV = \
      Rad_Conv ( Th=40, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel, AirSpeed=self.Vent_AirSpeed ) 
    self.P35_Rad_VV, self.P35_Conv_VV, self.P35_Tot_VV = \
      Rad_Conv ( Th=20+self.Px, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel, AirSpeed=self.Vent_AirSpeed ) 
    self.P50_Rad_VV, self.P50_Conv_VV, self.P50_Tot_VV = \
      Rad_Conv ( Th=70, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel, AirSpeed=self.Vent_AirSpeed ) 
    self.P60_Rad_VV, self.P60_Conv_VV, self.P60_Tot_VV = \
      Rad_Conv ( Th=80, Tl=20, 
                 Hoogte=self.Hoogte, Breedte=self.Breedte, 
                 N_Panel=self.N_Panel, N_Lamel=self.N_Lamel, AirSpeed=self.Vent_AirSpeed ) 


  # ***********************************************
  def __repr__ ( self ) :
    Line    = ""
    Line   += "Name           = %s\n" % self.Name

    if PrintLevel > 3 :
      Line += "Breedte        = %s [m]\n" % self.Breedte
      Line += "Hoogte         = %s [m]\n" % self.Hoogte
      Line += "Oppervlakte    = %s [m2]\n" % self.Opp
      Line += "Type           = %s\n" % self.Type
      if self.Vent_Aantal > 0 :
        Line += "Ventilator     = %i * %i [m3/hr]\n" % ( self.Vent_Aantal, self.Vent_Flow )


    if PrintLevel > 3 :
      Line += "\n"
      Line += "Type=%s   Hoogte=%s[m]   Breedt=%s[m]    Lamel-eff=%s     emmissiviteit=%s\n" % ( 
              self.Type, self.Hoogte, self.Breedte, Lamel_Eff, Emissiviteit )   
      if self.Vent_Aantal > 0 :
        Line += "Ventilator, N=%i, Flow=%i[m3/hr],  Forced AirSpeed = %.1f [m/s]\n" % ( 
            self.Vent_Aantal, self.Vent_Flow, self.Vent_AirSpeed ) 
      if self.P20_Tot != self.P20 :
        Line += "P20-Fabrikant   = %s [W]\n" % ( self.P20 )
      Line   += "P20-Totaal      = %s [W]\n" % ( self.P20_Tot )
      Line   += "P20-Radiation   = %s [W]\n" % self.P20_Radiation
      Line   += "P20-Convection  = %s [W]\n" % self.P20_Convection
      Line   += "P20 Rad / Conv  = %i %%  /  %i %%\n" % ( self.P20_perc_Radiation, self.P20_perc_Convection )
      if self.Vent_Aantal > 0 :
        Line += "P20-Forced-Conv = %i [W]\n" %  ( self.P20_Conv_VV )
        Line += "P20-Forced-Tot  = %i [W]\n" %  ( self.P20_Tot_VV )
      Line   += "\n"

      Line += "Type=%s   Hoogte=%s[m]   Breedt=%s[m]    Lamel-eff=%s     emmissiviteit=%s\n" % ( 
              self.Type, self.Hoogte, self.Breedte, Lamel_Eff, Emissiviteit )   
      if self.Vent_Aantal > 0 :
        Line += "Ventilator, N=%i, Flow=%i[m3/hr],  Forced AirSpeed = %.1f [m/s]\n" % ( 
            self.Vent_Aantal, self.Vent_Flow, self.Vent_AirSpeed ) 
      if self.P35_Tot != self.P35 :
        Line += "P%i-Fabrikant   = %s [W]\n" % ( self.Px, self.P35 )
      Line   += "P%i-Totaal      = %s [W]\n" % ( self.Px, self.P35_Tot )
      Line   += "P%i-Radiation   = %s [W]\n" % ( self.Px, self.P35_Radiation )
      Line   += "P%i-Convection  = %s [W]\n" % ( self.Px, self.P35_Convection )
      Line   += "P%i Rad / Conv  = %i %%  /  %i %%\n" % ( self.Px, self.P35_perc_Radiation, self.P35_perc_Convection )
      if self.Vent_Aantal > 0 :
        Line += "P%i-Forced-Conv = %i [W]\n" %  ( self.Px, self.P35_Conv_VV )
        Line += "P%i-Forced-Tot  = %i [W]\n" %  ( self.Px, self.P35_Tot_VV )
      Line   += "\n"

      Line += "Type=%s   Hoogte=%s[m]   Breedt=%s[m]    Lamel-eff=%s     emmissiviteit=%s\n" % ( 
              self.Type, self.Hoogte, self.Breedte, Lamel_Eff, Emissiviteit )   
      if self.Vent_Aantal > 0 :
        Line += "Ventilator, N=%i, Flow=%i[m3/hr],  Forced AirSpeed = %.1f [m/s]\n" % ( 
            self.Vent_Aantal, self.Vent_Flow, self.Vent_AirSpeed ) 
      if self.P50_Tot != self.P50 :
        Line += "P50-Fabrikant   = %s [W]\n" % ( self.P50 )
      Line   += "P50-Totaal      = %s [W]\n" % ( self.P50_Tot )
      Line   += "P50-Radiation   = %s [W]\n" % self.P50_Radiation
      Line   += "P50-Convection  = %s [W]\n" % self.P50_Convection
      Line   += "P50 Rad / Conv  = %i %%  /  %i %%\n" % ( self.P50_perc_Radiation, self.P50_perc_Convection )
      if self.Vent_Aantal > 0 :
        Line += "P50-Forced-Conv = %i [W]\n" %  ( self.P50_Conv_VV )
        Line += "P50-Forced-Tot  = %i [W]\n" %  ( self.P50_Tot_VV )
      Line   += "\n"

      Line += "Type=%s   Hoogte=%s[m]   Breedt=%s[m]    Lamel-eff=%s     emmissiviteit=%s\n" % ( 
              self.Type, self.Hoogte, self.Breedte, Lamel_Eff, Emissiviteit )   
      if self.Vent_Aantal > 0 :
        Line += "Ventilator, N=%i, Flow=%i[m3/hr],  Forced AirSpeed = %.1f [m/s]\n" % ( 
            self.Vent_Aantal, self.Vent_Flow, self.Vent_AirSpeed ) 
      if self.P60_Tot != self.P60 :
        Line += "P60-Fabrikant   = %s [W]\n" % ( self.P60 )
      Line   += "P60-Totaal      = %s [W]\n" % ( self.P60_Tot )
      Line   += "P60-Radiation   = %s [W]\n" % self.P60_Radiation
      Line   += "P60-Convection  = %s [W]\n" % self.P60_Convection
      Line   += "P60 Rad / Conv  = %i %%  /  %i %%\n" % ( self.P60_perc_Radiation, self.P60_perc_Convection )
      if self.Vent_Aantal > 0 :
        Line += "P60-Forced-Conv = %i [W]\n" %  ( self.P60_Conv_VV )
        Line += "P60-Forced-Tot  = %i [W]\n" %  ( self.P60_Tot_VV )
    return Line
  
# ***************************************************************************
# ***************************************************************************
if __name__ == '__main__':
  Hoogte  = 0.7
  X = Heat_Transfer ()

  # *******************************************************
  # Warmteoverdrachtscoefficient als functie van de Delta_T
  # *******************************************************
  for Delta_T in [ 20, 30, 40, 50, 60 ] :
    X.Convection_h ( Delta_T, Hoogte ) 
    print ( "%i [Celsius]  ==>  %.1f [W/m2.K]" % ( Delta_T, X.WOC ) )
  print ( X )
  
  # *******************************************************
  # Warmteoverdrachtscoefficient als functie van de forced airspeed
  # *******************************************************
  Delta_T = 20
  for AirSpeed in [ 0.2, 0.3, 0.4, 0.5, 0.7, 1, 1.5, 2, 3 ] :
    X.Convection_h ( Delta_T, Hoogte, AirSpeed ) 
    print ( "%.1f [m/s]  ==>  %.1f [W/m2.K]     Gr/Re^2=%.2f   %.1f" % ( 
            AirSpeed, X.WOC, X.Grashof_Reynolds, X.h_WOC_Forced ) )
  print ( X )
  
  
  Radiator_Achter = Radiator_Class ( "Achter", Breedte = 1000, Hoogte = 700, Type = 33, Px=30 )
  Radiator_Achter.Add_Ventilator (  Aantal=5, Diameter=12, Flow=126 ) 
  print ( Radiator_Achter )
   
  #Radiator_Beter = Radiator_Class ( "Achter", Breedte = 1000, Hoogte = 700, Type = 33 )
  #Radiator_Beter.Add_Ventilator (  Aantal=10, Diameter=12, Flow=126 ) 
  #print ( Radiator_Beter )

  """
  for RType in [ 11, 21, 22, 33 ] :
    Radson1 = Radiator_Class ( "Radson1", Breedte = 450, Hoogte = 900, Type = RType )
    print ( Radson1 )
  ##"""
   
