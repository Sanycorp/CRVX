# Manually mark whatever you are looking at / nearest non-player entity as a target
tag @e[c=1,type=!player,type=!aegis:primordial_sentinel,r=16] add aegis_target
tellraw @s {"rawtext":[{"text":"§b[Aegis]§r §7Nearest entity marked for nullification."}]}
