
import sys 
import numpy as np
from unittest import TestCase, main
from collections import OrderedDict
from scipy import sparse
from scipy import optimize
#from scipy.fftpack import rfft, irfft, fft, ifft
from numpy.fft import rfft, irfft, fft, ifft
import time
import matplotlib.pyplot as plt
import numdifftools as nd
from scipy.sparse.linalg import LinearOperator

from pyfeti.src.nonlinalg import NonLinearOperator
from pyfeti.src.nonlinear import NonLinearLocalProblem, NonlinearSolverManager 
from pyfeti.src.optimize import feti as FETIsolver
from pyfeti.src.optimize import newton


class  Test_NonlinearSolver(TestCase):
    def setup_1D_linear_localproblem(self,nH = 1, beta = 0.0, alpha = 0.0):
        '''
        setup a simple one 1 problem with 2
       linear domains

                F->            <-F
        |>------0------0  0------0-------<|

        Parameters:
            nH : int
                number of Harmonics to be considered
            beta : float
                Stiffness coefficient for linear Damping, C = alpha*M + beta*K
            alpha : float
                Mass coefficient for linear Damping, C = alpha*M + beta*K
        returns :
            Z1, Z2, B1, B2, fn1_, fn2_

        '''

        K1 = np.array([[2.0,-1.0],
                       [-1.0,1.0]])

        K2 = np.array([[1.0,-1.0],
                       [-1.0,2.0]])


        M1 = np.array([[1.0,0.0],
                       [0.0,1.0]])

        M2 = M1
        

        
        C1 = alpha*M1 + beta*K1
        C2 = alpha*M2 + beta*K2


        #f = np.array([1.0,3.0])
        
        B1 = {(1,2): np.kron(np.eye(nH),np.array([[0.0,1.0]]))}
        B2 = {(2,1): np.kron(np.eye(nH),np.array([[-1.0,0.0]]))}


 
        f1_ = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])), np.array([1.0,0.0]))
        f2_ = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])),np.array([0.0,-1.0]))

        cfn1_ = lambda u_,w=np.zeros(nH) : -f1_
        cfn2_ = lambda u_,w=np.zeros(nH) : -f2_

        JZ1 =  lambda u_,w=np.zeros(nH) : np.kron(-np.diag(w**2),M1) + 1J*np.kron(np.diag(w**2),C1) + np.kron(np.eye(w.shape[0]),K1)
        JZ2 =  lambda u_,w=np.zeros(nH) : np.kron(-np.diag(w**2),M2) + 1J*np.kron(np.diag(w**2),C2) + np.kron(np.eye(w.shape[0]),K2)

        callback_func = lambda u_,w=np.zeros(nH) : JZ1(u_,w).dot(u_)
        Z1 = NonLinearOperator(callback_func , shape=JZ1(0).shape, jac=JZ1)
        fn1_ = NonLinearOperator(cfn1_ , shape=JZ1(0).shape, jac=np.zeros(JZ1(0).shape))
        
        callback_func2 = lambda u_,w=np.zeros(nH) : JZ2(u_,w).dot(u_)
        Z2 = NonLinearOperator(callback_func2 , shape=JZ2(0).shape, jac=JZ2)
        fn2_ = NonLinearOperator(cfn2_ , shape=JZ2(0).shape, jac=np.zeros(JZ2(0).shape))

       
        return Z1, Z2,B1, B2, fn1_, fn2_

    def setup_1D_nonlinear_localproblem(self,nH = 1, beta = 0.0, alpha = 0.0, c = 0.0):
        '''
        setup a simple one 1 problem with 2
        linear domains

                   F->            <-F
        |>-*---*---0------0  0------0-------<|
           |/\/|                        
       nonlinear spring            

        Parameters:
            nH : int
                number of Harmonics to be considered
            beta : float
                Stiffness coefficient for linear Damping, C = alpha*M + beta*K
            alpha : float
                Mass coefficient for linear Damping, C = alpha*M + beta*K
            c  : float
                nonlinear spring coefficinet

        returns :
            Z1, Z2, B1, B2, fn1_, fn2_

        '''

        ndof = 2
        Z1, Z2,B1, B2, fn1_, fn2_ = self.setup_1D_linear_localproblem(nH,beta,alpha)


        f1_ = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])), np.array([1.0,0.0]))
        f2_ = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])),np.array([0.0,-1.0]))

        # FFT time domain to freq, iFFT freq to time
        
        mode  = 'ortho'
        FFT = lambda u : rfft(u,norm=mode).T[0:nH+1].reshape((nH+1)*ndof,1).flatten()[ndof:] # removing the static part
        iFFT = lambda u_ : 2.0*np.real(ifft(np.concatenate((np.zeros(ndof),u_)).reshape(nH+1,ndof).T, n=100,norm=mode))

        # nonlinear force in Time
        fnl = lambda u, n=3 : c*np.array([u[0]**n, u[1]*0.0])
        fnl_ = lambda u_, n=3 : FFT(fnl(iFFT(u_),n))

        u_ = np.array([1.0]*ndof*nH, dtype=np.complex)
        u_[1:] = 0.0
        #u_[3:] = 0.0
        #u_[0:2] = 0.0
        
        np.testing.assert_almost_equal(u_, FFT(iFFT(u_)), decimal=8)

        cfn1_ = lambda u_, w=np.zeros(nH) : -f1_ + fnl_(u_)
        
        fn1_ = NonLinearOperator(cfn1_ , shape=Z1.shape, jac=np.zeros(Z1.shape))
        

        return Z1, Z2,B1, B2, fn1_, fn2_
        
    def test_1D_linear_localproblem(self):

        nH = 2 # number of Harmonics
        Z1, Z2,B1, B2, fn1_, fn2_ = self.setup_1D_linear_localproblem(nH)

        JZ1 = Z1.jac

        length = fn1_.shape[0]
        nonlin_obj1 = NonLinearLocalProblem(Z1,B1,fn1_,length)
        nonlin_obj2 = NonLinearLocalProblem(Z2,B2,fn2_,length)

        # Defining a Harmonic Lambda = 0
        lambda_dict = {}
        lambda_dict[(1,2)] = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])), np.array([0.0]))
        lambda_dict[(2,1)] = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])), np.array([0.0]))

        freq_list = np.arange(0.0,1.0,0.01)
        u_target_1 = np.zeros(freq_list.shape[0],dtype=np.complex)
        u_calc_1 = np.zeros(freq_list.shape[0],dtype=np.complex)
        
        for i,freq in enumerate(freq_list):
            w = 2.0*np.pi*freq*np.arange(1,nH+1)

            # using linear solver
            ui_ = np.linalg.solve(JZ1(0,w),-fn1_.eval(0,w))
            u_target_1[i] = ui_[0]

            # using nonlinear solver 
            ui_calc = nonlin_obj1.solve(lambda_dict,w)
            u_calc_1[i] = ui_calc[0]

        np.testing.assert_almost_equal(u_target_1, u_calc_1, decimal=8)
        
        # plotting frequency response
        if False:            
            ax = plt.axes()
            ax.plot(np.abs(u_target_1),'r--',label='target')
            ax.plot(np.abs(u_calc_1),'b*',label='calc')
            plt.legend()
            plt.show()

    def l_array2dict(self,l):
            nH = self.nH
            lambda_dict = {}
            #lambda_dict[(1,2)] = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])), l)
            #lambda_dict[(2,1)] = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])), l)
            lambda_dict[(1,2)] = l
            lambda_dict[(2,1)] = l
            return  lambda_dict

    def test_1D_linear_localproblem_2(self):
        nH = 1
        Z1, Z2,B1, B2, fn1_, fn2_ = self.setup_1D_linear_localproblem(nH,beta=0.1)
        length = fn1_.shape[0]
        nonlin_obj1 = NonLinearLocalProblem(Z1,B1,fn1_,length)
        nonlin_obj2 = NonLinearLocalProblem(Z2,B2,fn2_,length)


        int_force_list = np.arange(0.0,1.0,1.0)
        freq_list = np.arange(0.0,0.5,0.02)
        u_calc_list = []
        u_calc_list_2 = []
        r_list =[]
        for freq in freq_list:
            w = 2.0*np.pi*freq*np.arange(1,nH+1)
            u_calc_1 = []
            u_calc_2 = []
            r_calc = []
            
            for int_force in int_force_list:

                lambda_dict = {}
                lambda_dict[(1,2)] = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])), np.array([int_force]))
                lambda_dict[(2,1)] = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])), np.array([int_force]))
            
                # using nonlinear solver 
                ui_calc = nonlin_obj1.solve(lambda_dict,w)
                uj_calc = nonlin_obj2.solve(lambda_dict,w)
                if (ui_calc is not None) and (uj_calc is not None):
                    u_calc_1.append(ui_calc[1])
                    u_calc_2.append(uj_calc[0])
                    r_calc.append(np.linalg.norm(B1[1,2].dot(ui_calc) + B2[2,1].dot(uj_calc)))
                #else:
                #    u_calc_1, u_calc_2, r_calc = None, None, None

                u_calc_list.append(u_calc_1)
                u_calc_list_2.append(u_calc_2)
                r_list.append(r_calc)

        # plotting forced responde varing interface force (lambda)                        
        if False:            
            ax = plt.axes()
            for int_force, u_calc in zip(int_force_list,u_calc_list):
                ax.plot(np.abs(u_calc),'ro', label=('D1, $\lambda$ = %2.2e' %int_force))

            for int_force, u_calc in zip(int_force_list,u_calc_list_2):
                ax.plot(np.abs(u_calc),'b*', label=('D2, $\lambda$ = %2.2e' %int_force))
            
            plt.legend()
            plt.show()


        # plotting interface residual varing interface force (lambda) and frequency                       
        if False:  
            ax = plt.axes()
            lambda_list = []
            min_r_list = []
            for freq, r in zip(freq_list,r_list):
                min_r_id = np.argmin(r)
                fb = int_force_list[min_r_id]
                lambda_list.append(fb)
                min_r_list.append(r[min_r_id])
            ax.plot(freq_list,lambda_list,'--')
            ax.set_xlabel('Frequency [Hz]')
            ax.set_ylabel('$\lambda$ [N]')

            
            fig2, ax1 = plt.subplots(1,1)
            ax1.plot(freq_list,min_r_list,'--')
            ax1.set_xlabel('Frequency [Hz]')
            ax1.set_ylabel('$\Delta u$ [mm]')

            
            plt.show()

    def test_1D_linear_dual_interface_problem(self):
        ''' Test linear problem with no Damping
        '''
        nH,c,beta,alpha = 1, 0.0, 0.0, 0.0
        Rb,nc,nH, nonlin_obj_list,JRb = self.setup_nonlinear_problem(nH,c,beta,alpha) 
        self.run_dual_interface_problem(Rb,nc,nH, nonlin_obj_list,jac=JRb)

    def test_1D_linear_dual_interface_nonlinear_problem(self):
        ''' Test nonlinear problem with Damping
        '''
        nH,c,beta,alpha = 1, 3.0, 1.8, 0.0
        Rb,nc,nH, nonlin_obj_list,JRb = self.setup_nonlinear_problem(nH,c,beta,alpha) 
        self.run_dual_interface_problem(Rb,nc,nH, nonlin_obj_list,jac=JRb)
  
    def setup_nonlinear_problem(self,nH=1,c=0.0,beta=0.18,alpha=0.0):
        
       
        self.nH = nH
        Z1, Z2,B1, B2, fn1_, fn2_ = self.setup_1D_nonlinear_localproblem(nH,c=c, beta = beta, alpha=alpha)
        length = fn1_.shape[0]
        nonlin_obj1 = NonLinearLocalProblem(Z1,B1,fn1_,length)
        nonlin_obj2 = NonLinearLocalProblem(Z2,B2,fn2_,length)

        # defining the Residual at the interface
        Rb_ = lambda w0 : lambda l : B1[1,2].dot(nonlin_obj1.solve(self.l_array2dict(l),w0)) + \
                                    B2[2,1].dot(nonlin_obj2.solve(self.l_array2dict(l),w0))        

        Rb = lambda w0 : lambda l : nonlin_obj1.solve_interface_displacement(self.l_array2dict(l),w0)[1,2] + \
                                    nonlin_obj2.solve_interface_displacement(self.l_array2dict(l),w0)[2,1]

        JRb = lambda w0 : lambda l : nonlin_obj1.derivative_u_over_lambda(w0)[1,2] + \
                                    nonlin_obj2.derivative_u_over_lambda(w0)[2,1]

        w = 0.0
        Rl= Rb(w)
        Rl_= Rb_(w)
        nc = B1[1,2].shape[0]
        Rb = Rb_
        l0 = np.ones(nc, dtype=np.complex)
        l0 = np.kron(np.concatenate(([1.0,],(nH-1)*[0.0])), l0)
        
        nonlin_obj_list = [nonlin_obj1, nonlin_obj2]
    
        return Rb,nc,nH, nonlin_obj_list,JRb

    def test_compare_FETI_vs_explicit_inverse(self):
        ''' The Dual Nonlinear problem need to solve the linear system of the newton iteration

        F * delta_l = error

        F can be explicit assembled, but it needs a matrix mpi communication
        otherwise, a FETI solver can be use to solve Newton iteration

        '''
        nH,c,beta,alpha = 1, 3.0, 1.8, 0.0
        Rb,nc,nH, nonlin_obj_list,JRb = self.setup_nonlinear_problem(nH,c,beta,alpha) 
        

        f = 0.0
        w0 = w = 2.0*np.pi*f*np.arange(1,nH+1)
        tol = 1.0e-8
        Rl= Rb(w)
        JRl = JRb(w)
        l0 = np.ones(nc, dtype=np.complex)


        lambda_dict = self.l_array2dict(l0)
        nonlinear_problem_dict = {}
        nonlinear_problem_dict[1] = nonlin_obj_list[0]
        nonlinear_problem_dict[2] = nonlin_obj_list[1]
        local_problem_dict = {}
        for key, nonlinear_obj in nonlinear_problem_dict.items():
            local_problem_dict[key] = nonlinear_obj.build_linear_problem(lambda_dict,w0,u=None)

        r0 = Rl(l0)
        x_target = np.linalg.solve(JRl(l0),r0)
        x = FETIsolver(local_problem_dict)

        e = np.abs(x - x_target)
        np.testing.assert_array_almost_equal(x,x_target,decimal=10)
        
        x=1
            
    def run_dual_interface_problem(self,Rb,nc,nH, nonlin_obj_list = [],jac=None):

        try:
            nonlin_obj1  = nonlin_obj_list[0]
            nonlin_obj2 = nonlin_obj_list[1]
        except:
            pass
        
        lambda_list = []
        min_r_list = []
        freq_list = []
        u1_list = []
        u2_list = []
        l0 = np.zeros(nc, dtype=np.complex)
        freq_init = 0.0
        delta_freq = 0.01
        n_int = 150
        default_scalling = 1
        scalling = 1
        factor = 0.9
        freq = freq_init
        count = 0
        forward = True
        jump = True
        for n in range(n_int):
            w = 2.0*np.pi*freq*np.arange(1,nH+1)
            tol = 1.0e-8
        
            Rl= Rb(w)
            
            sol = None
            try:

                #sol = optimize.root(Rl, l0, method='lm', jac=JRl_num, options={'fatol': tol, 'maxiter' : 20})
                #sol = optimize.root(Rl, l0, method='krylov', options={'fatol': tol, 'maxiter' : 20})
                JRl = jac(w)
                sol = newton(Rl,JRl,l0)
                #sol = optimize.root(Rl, l0, method='lm', options={'fatol': tol, 'maxiter' : 20})
                print('Number of iterations %i' %sol.nit)
                if sol.success:
                    # restart success counter
                    count = 0
                    scalling = default_scalling
                    l0 =  sol.x
                    r_vec = sol.fun
                    r = np.linalg.norm(r_vec )
                    np.testing.assert_almost_equal(r, 0.0, decimal=8)

                    min_r_list.append(r)
                    lambda_list.append(l0)

                    freq_list.append(freq)
                    u1 = nonlin_obj1.u_init
                    u2 = nonlin_obj2.u_init

                    u1_list.append(u1)
                    u2_list.append(u2)

                    
                    JLO = lambda l : LinearOperator(shape=(1,1), dtype=np.complex, matvec = lambda v : JRl(l).dot(v))
                    #JRl_num = nd.Jacobian(Rl,n=1)

                    JRl_eval = JRl(l0)
                    #JRl_num_eval = JRl_num(l0)
                    #np.testing.assert_array_almost_equal(JRl_eval,JRl_num_eval,decimal=10)
                else:
                    raise Exception
            except:
                count +=1
                 
                print('Interface Problem did not converge! Try number %i' %count)
                if count>3:
                    # jump
                    if jump:
                        freq += 15*delta_freq*default_scalling
                        freq_jump = freq
                        jump=False
                    else:
                        freq = freq_jump
                        jump = True

                    print('Frequency jump = %2.2e' %freq_jump)
                    # go backwards
                    if forward:
                        factor=0.9
                        scalling = -default_scalling
                        forward=False
                    #go forward again
                    else:
                        factor = 1.0
                        scalling = default_scalling
                        forward=True
                    count = 0
                    
                else:
                    freq = freq_list[-1]
                scalling = scalling*factor


            freq += delta_freq*scalling
            
        plot_results = False
        if plot_results:
            fig1, ((ax1,ax2),(ax3,ax4)) = plt.subplots(2,2)
            ax1.plot(freq_list,np.abs(lambda_list),'*--')
            ax1.set_xlabel('Frequency [Hz]')
            ax1.set_ylabel('$\lambda$ [N]')

            #fig2, ax2 = plt.subplots(1,1)
            ax2.plot(freq_list,min_r_list,'*--')
            ax2.set_xlabel('Frequency [Hz]')
            ax2.set_ylabel('$\Delta u$ [mm]')
            

            #fig3, ax3 = plt.subplots(1,1)
            ax3.plot(freq_list,np.abs(u1_list),'*--')
            ax3.set_xlabel('Frequency [Hz]')
            ax3.set_ylabel(' u1 [mm]')

            #fig4, ax4 = plt.subplots(1,1)
            ax4.plot(freq_list,np.abs(u2_list),'*--')
            ax4.set_xlabel('Frequency [Hz]')
            ax4.set_ylabel(' u2 [mm]')
            
            plt.show()

    def Test_NonlinearSolverManager(self):
        nH,c,beta,alpha = 1, 0.0, 1.0, 0.0
        Z1, Z2,B1, B2, fn1_, fn2_ = self.setup_1D_nonlinear_localproblem(nH,c=c, beta = beta, alpha=alpha)
        Z_dict = {1:Z1,2:Z2}
        B_dict = {1:B1,2:B2}
        f_dict = {1:fn1_,2:fn2_}
        manager = NonlinearSolverManager(Z_dict,B_dict,f_dict)
        manager.build_local_to_global_mapping()
        manager.lambda_init = np.zeros(manager.lambda_size, dtype=manager.dtype)
        

        freq_list = np.arange(0,0.5,0.01)
        lambda_list = []
        for freq in freq_list:
            w0 = 2.0*np.pi*freq
            try:
                sol = manager.solve_dual_interface_problem(w0=np.array([w0]))
                lambda_sol = sol.x
                manager.lambda_init = lambda_sol
            except:
                sol = manager.solve_dual_interface_problem(w0=np.array([w0]))
                lambda_sol = 0.0
            lambda_list.append(lambda_sol)
            

        plt.plot(freq_list,np.abs(lambda_list),'o')
        plt.show()
        
        x=1




if __name__=='__main__':

    #main()
    testobj = Test_NonlinearSolver()
    #testobj.test_1D_linear_localproblem()
    #testobj.test_1D_linear_dual_interface_problem()
    #testobj.setup_1D_nonlinear_localproblem()
    #testobj.test_1D_linear_dual_interface_nonlinear_problem()
    #testobj.test_compare_FETI_vs_explicit_inverse()
    #testobj.test_1D_linear_localproblem_2()
    testobj.Test_NonlinearSolverManager()