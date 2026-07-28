!> Fortran interface to wss_profiler.
!> 
!> Usage:
!>   use wss_profiler_mod
!>   call wss_init()
!>   call wss_begin()
!>   call some_kernel(...)
!>   call wss_end_named("kernel_name")
!>
!> Link with: -lwss_profiler -lpapi
module wss_profiler_mod
  use iso_c_binding
  implicit none

  interface
    subroutine wss_init() bind(C, name="wss_init_")
    end subroutine

    subroutine wss_begin() bind(C, name="wss_begin_")
    end subroutine

    subroutine wss_end_c(name, name_len) bind(C, name="wss_end_")
      use iso_c_binding
      character(kind=c_char), intent(in) :: name(*)
      integer(c_int), value :: name_len
    end subroutine
  end interface

contains

  subroutine wss_end_named(name)
    character(len=*), intent(in) :: name
    call wss_end_c(name, len_trim(name))
  end subroutine

end module wss_profiler_mod
